"""Viva examination endpoints for the Phase 3 speech pipeline."""

import asyncio
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.config import get_settings
from app.models.answer import Answer
from app.models.assessment import Assessment
from app.models.assignment import Assignment
from app.models.consent import Consent
from app.models.course import Course
from app.models.question import Question, QuestionDifficulty
from app.models.topic import Topic
from app.models.user import User, UserRole
from app.models.viva_session import VivaSession, VivaStatus
from app.schemas.viva import (
    BehaviorFlagCreate,
    InterviewTurnRequest,
    VivaConfig,
    VivaStartRequest,
)
from app.services.adaptive_service import AdaptiveVivaService
from app.services.conversational_service import ConversationalService
from app.services.eval_service import evaluate_answer
from app.services.llm_service import get_provider
from app.services.speech_service import SpeechService
from app.services.viva_orchestrator import VivaOrchestrator
from app.utils.text import anonymise, clean_transcript

router = APIRouter(prefix="/viva", tags=["Viva Examination"])
_SESSION_LOCKS: dict[uuid.UUID, asyncio.Lock] = {}


async def _process_interview_turn(
    session_id: uuid.UUID,
    payload: InterviewTurnRequest,
    current_user: User,
    db: AsyncSession,
) -> dict[str, Any]:
    """Serialize turns for one session to prevent retries racing state changes."""
    lock = _SESSION_LOCKS.setdefault(session_id, asyncio.Lock())
    async with lock:
        return await _process_interview_turn_locked(session_id, payload, current_user, db)


async def _process_interview_turn_locked(
    session_id: uuid.UUID,
    payload: InterviewTurnRequest,
    current_user: User,
    db: AsyncSession,
) -> dict[str, Any]:
    """Score and persist one live transcript, then prepare a contextual next turn."""
    session_result = await db.execute(select(VivaSession).where(VivaSession.id == session_id))
    session = session_result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Interview session not found")
    if session.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="You do not have access to this interview")
    if session.status.value != "in_progress":
        raise HTTPException(status_code=409, detail="This interview is no longer in progress")

    question_result = await db.execute(select(Question).where(Question.id == payload.question_id))
    question = question_result.scalar_one_or_none()
    if question is None:
        raise HTTPException(status_code=404, detail="Interview question not found")

    order = list((session.config or {}).get("question_order", []))
    asked_index = session.current_question_index - 1
    if asked_index < 0 or asked_index >= len(order) or order[asked_index] != str(question.id):
        raise HTTPException(status_code=409, detail="This is not the current interview question")

    previous_answer = await db.execute(
        select(Answer.id).where(
            Answer.session_id == session_id,
            Answer.question_id == question.id,
        )
    )
    if previous_answer.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409, detail="An answer was already submitted for this question"
        )

    transcript = anonymise(clean_transcript(payload.transcript))
    if not transcript:
        raise HTTPException(status_code=422, detail="No speech was recognized. Please try again.")

    key_points = question.expected_key_points or (
        [question.explanation] if question.explanation else []
    )
    try:
        evaluation = await evaluate_answer(
            question=question.question_text,
            transcript=transcript,
            key_points=key_points,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    next_question: Question | None = None
    interviewer_text = "Thank you for sharing your answer. That concludes this interview."
    is_last_question = session.current_question_index >= session.max_questions

    if not is_last_question:
        history_result = await db.execute(
            select(Answer, Question)
            .join(Question, Answer.question_id == Question.id)
            .where(Answer.session_id == session_id)
            .order_by(Answer.sequence_number)
        )
        history_pairs = history_result.all()
        history = [
            f"Interviewer: {answered_question.question_text[:300]}\n"
            f"Candidate: {(answer.transcript or '')[-600:]}"
            for answer, answered_question in history_pairs
        ]
        history.append(
            f"Interviewer: {question.question_text[:300]}\nCandidate: {transcript[-1000:]}"
        )
        course = await db.scalar(select(Course).where(Course.id == session.course_id))
        topic_result = await db.execute(select(Topic).where(Topic.course_id == session.course_id))
        course_topics = topic_result.scalars().all()
        configured_topic_ids = set((session.config or {}).get("topic_ids", []))
        if configured_topic_ids:
            course_topics = [
                topic for topic in course_topics if str(topic.id) in configured_topic_ids
            ]
        topic_by_id = {str(topic.id): topic for topic in course_topics}
        if not topic_by_id:
            raise HTTPException(status_code=503, detail="This course has no interview topics.")

        follow_up_depth = int((session.config or {}).get("follow_up_depth", 0))
        eligible_topics = course_topics
        if follow_up_depth >= 2:
            other_topics = [item for item in course_topics if item.id != question.topic_id]
            if other_topics:
                eligible_topics = other_topics

        is_adaptive = AdaptiveVivaService.is_adaptive_session(session)
        if is_adaptive:
            session_scores = [
                float(
                    a.fused_score
                    if a.fused_score is not None
                    else (a.llm_score if a.llm_score is not None else a.embedding_score or 0.5)
                )
                for a, _ in history_pairs
            ]
            session_scores.append(float(evaluation["fused_score"]))
            base_diff = (session.config or {}).get("difficulty") or "medium"
            progression = list((session.config or {}).get("difficulty_progression", []))
            curr_diff = progression[-1] if progression else base_diff
            target_diff = AdaptiveVivaService.compute_next_difficulty(curr_diff, session_scores)

            asked_set = set(order[: session.current_question_index])
            asked_set.add(str(question.id))
            for a_id_str in (session.config or {}).get("asked_question_ids", []):
                asked_set.add(str(a_id_str))

            eligible_topic_uuids = [t.id for t in eligible_topics]
            upcoming_ids = order[session.current_question_index :]
            if upcoming_ids:
                approval_cond = Question.is_approved.is_(True) | Question.id.in_(
                    [uuid.UUID(x) for x in upcoming_ids]
                )
            else:
                approval_cond = Question.is_approved.is_(True)

            candidate_stmt = (
                select(Question, Topic)
                .join(Topic, Question.topic_id == Topic.id)
                .where(
                    Topic.id.in_(eligible_topic_uuids),
                    approval_cond,
                )
            )
            if asked_set:
                candidate_stmt = candidate_stmt.where(
                    Question.id.not_in([uuid.UUID(x) for x in asked_set if x])
                )

            candidate_result = await db.execute(
                candidate_stmt.order_by(
                    (Question.difficulty == target_diff).desc(),
                    Question.times_used.asc(),
                    Question.created_at.asc(),
                ).limit(6)
            )
        else:
            upcoming_ids = order[session.current_question_index :]
            candidate_result = (
                await db.execute(
                    select(Question, Topic)
                    .join(Topic, Question.topic_id == Topic.id)
                    .where(
                        Question.id.in_([uuid.UUID(item) for item in upcoming_ids]),
                        Topic.course_id == session.course_id,
                    )
                    .order_by(Question.times_used.asc(), Question.created_at.asc())
                    .limit(4)
                )
                if upcoming_ids
                else None
            )
        candidates = candidate_result.all() if candidate_result is not None else []
        candidate_questions = [
            {
                "id": str(candidate.id),
                "question": candidate.question_text[:350],
                "topic": topic.name[:120],
                "difficulty": candidate.difficulty.value,
                "question_type": candidate.question_type or "unspecified",
                "expected_concepts": [
                    concept[:120] for concept in (candidate.expected_key_points or [])[:3]
                ],
            }
            for candidate, topic in candidates
        ]
        bank_ids = [item["id"] for item in candidate_questions]
        allowed_topic_ids = [str(item.id) for item in eligible_topics]
        schema = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "ask_question",
                        "ask_follow_up",
                        "move_to_next_topic",
                        "complete_interview",
                    ],
                },
                "acknowledgement": {"type": "string"},
                "question": {"type": "string"},
                "topic_id": {"type": "string", "enum": allowed_topic_ids},
                "question_source": {"type": "string", "enum": ["question_bank", "generated"]},
                "question_bank_id": {
                    "type": "string",
                    "enum": [*bank_ids, "__generated__"],
                },
                "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
                "question_type": {
                    "type": "string",
                    "enum": ["conceptual", "practical", "analytical", "application"],
                },
                "is_cross_question": {"type": "boolean"},
                "reason": {"type": "string"},
                "expected_concepts": {"type": "array", "items": {"type": "string"}},
                "coverage_update": {
                    "type": "object",
                    "properties": {
                        "topic_id": {"type": "string", "enum": allowed_topic_ids},
                        "status": {
                            "type": "string",
                            "enum": ["in_progress", "covered", "needs_review"],
                        },
                    },
                    "required": ["topic_id", "status"],
                    "additionalProperties": False,
                },
            },
            "required": [
                "action",
                "acknowledgement",
                "question",
                "topic_id",
                "question_source",
                "question_bank_id",
                "difficulty",
                "question_type",
                "is_cross_question",
                "reason",
                "expected_concepts",
                "coverage_update",
            ],
            "additionalProperties": False,
        }
        analysis = (course.syllabus_analysis or {}) if course else {}
        eligible_names = {item.name.casefold() for item in eligible_topics}
        syllabus_modules = []
        for module in analysis.get("modules", []):
            if not isinstance(module, dict):
                continue
            for syllabus_topic in module.get("topics", []):
                if (
                    not isinstance(syllabus_topic, dict)
                    or not isinstance(syllabus_topic.get("name"), str)
                    or syllabus_topic["name"].casefold() not in eligible_names
                ):
                    continue
                topic_context = {
                    "module": str(module.get("name") or "")[:120],
                    "name": syllabus_topic["name"][:120],
                    "subtopics": [
                        item[:120]
                        for item in syllabus_topic.get("subtopics", [])[:3]
                        if isinstance(item, str)
                    ],
                    "key_concepts": [
                        item[:120]
                        for item in syllabus_topic.get("key_concepts", [])[:3]
                        if isinstance(item, str)
                    ],
                }
                references = syllabus_topic.get("source_references", [])
                if course and course.syllabus_text:
                    topic_context["source_excerpts"] = [
                        course.syllabus_text[reference["start"] : reference["end"]][:400]
                        for reference in references[:1]
                        if isinstance(reference, dict)
                        if isinstance(reference.get("start"), int)
                        and isinstance(reference.get("end"), int)
                    ]
                syllabus_modules.append(topic_context)
                if len(syllabus_modules) >= 3:
                    break
            if len(syllabus_modules) >= 3:
                break
        raw_syllabus_excerpt = ""
        if course and course.syllabus_text and not syllabus_modules:
            raw_syllabus_excerpt = course.syllabus_text[:1000]
        prompt = (
            "You are conducting an adaptive oral interview using only the selected saved syllabus "
            "and this course's question bank. Assess the answer, choose one supported action, and "
            "return one concise specific acknowledgement plus the next question (unless complete). "
            "Prefer a suitable unused question-bank item. Otherwise generate a new question tied "
            "to a listed syllabus topic. Use the candidate's answer for a contextual follow-up, "
            "example, misconception check, or prerequisite question. Never repeat a prior question. "
            "After two consecutive follow-ups, move to another topic when possible. Do not reveal "
            "private reasoning; give only a short evidence-based reason. Return valid JSON only.\n"
            f"Course: {course.name if course else 'Unknown'}\n"
            f"Subject: {(course.subject or course.code) if course else 'Unknown'}\n"
            f"Academic level: {course.academic_level if course else 'Unspecified'}\n"
            f"Selected syllabus structure: {syllabus_modules}\n"
            f"Original syllabus excerpt: {raw_syllabus_excerpt}\n"
            f"Eligible syllabus topics: {[(str(item.id), item.name) for item in eligible_topics]}\n"
            f"Unused question-bank candidates: {candidate_questions}\n"
            f"Selected difficulty: {(session.config or {}).get('difficulty') or 'adaptive'}\n"
            f"Consecutive follow-up count: {follow_up_depth}\n"
            f"Candidate: {current_user.full_name}\n"
            f"Conversation so far:\n{chr(10).join(history[-4:])}\n"
            f"Answer evaluation (0-1): {evaluation['fused_score']:.2f}; "
            f"rubric evidence: {str(evaluation['rubric'].get('justification', ''))[:300]}"
        )
        try:
            generated = await get_provider().generate(prompt, schema=schema)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"The Groq interviewer could not prepare the next turn: {exc}",
            ) from exc
        if not isinstance(generated, dict):
            raise HTTPException(
                status_code=503, detail="The AI interviewer returned an invalid response."
            )
        action = generated.get("action")
        topic_id = generated.get("topic_id")
        question_source = generated.get("question_source")
        bank_question_id = generated.get("question_bank_id")
        acknowledgement = generated.get("acknowledgement")
        next_text = generated.get("question")
        expected_concepts = generated.get("expected_concepts")
        if (
            action
            not in {"ask_question", "ask_follow_up", "move_to_next_topic", "complete_interview"}
            or topic_id not in topic_by_id
            or not isinstance(acknowledgement, str)
            or not isinstance(next_text, str)
            or not isinstance(expected_concepts, list)
            or any(not isinstance(point, str) for point in expected_concepts)
            or not isinstance(generated.get("is_cross_question"), bool)
            or not isinstance(generated.get("coverage_update"), dict)
            or generated["coverage_update"].get("topic_id") != topic_id
            or generated["coverage_update"].get("status")
            not in {"in_progress", "covered", "needs_review"}
        ):
            raise HTTPException(
                status_code=503,
                detail="The AI interviewer returned a decision that failed validation.",
            )
        updated_config = dict(session.config or {})
        updated_config["topic_coverage"] = dict(updated_config.get("topic_coverage", {}))
        updated_config["topic_coverage"][topic_id] = generated["coverage_update"]["status"]
        session.config = updated_config
        if action == "complete_interview":
            interviewer_text = acknowledgement.strip() or interviewer_text
        else:
            next_text = next_text.strip()
            if not next_text or not acknowledgement.strip():
                raise HTTPException(
                    status_code=503,
                    detail="The AI interviewer returned an incomplete next question.",
                )
            if question_source == "question_bank":
                if bank_question_id not in bank_ids:
                    # Fallback check if the question exists in course or upcoming_ids
                    fallback_q = await db.get(Question, uuid.UUID(bank_question_id))
                    if (
                        fallback_q
                        and fallback_q.topic
                        and fallback_q.topic.course_id == session.course_id
                    ):
                        next_question = fallback_q
                        next_text = next_question.question_text
                    else:
                        raise HTTPException(
                            status_code=503,
                            detail="The AI selected a question outside the retrieved question bank.",
                        )
                else:
                    next_question = next(
                        candidate
                        for candidate, _ in candidates
                        if str(candidate.id) == bank_question_id
                    )
                    next_text = next_question.question_text
            elif question_source == "generated" and bank_question_id == "__generated__":
                cleaned_concepts = [point.strip() for point in expected_concepts if point.strip()]
                if not cleaned_concepts or topic_id not in topic_by_id:
                    raise HTTPException(
                        status_code=503,
                        detail="The AI generated a question without a valid topic or rubric.",
                    )
                selected_difficulty = (session.config or {}).get("difficulty")
                try:
                    difficulty = QuestionDifficulty(
                        selected_difficulty or generated.get("difficulty")
                    )
                except ValueError as exc:
                    raise HTTPException(
                        status_code=503, detail="The AI returned an invalid difficulty."
                    ) from exc
                next_question = Question(
                    topic_id=uuid.UUID(topic_id),
                    question_text=next_text,
                    expected_key_points=cleaned_concepts,
                    difficulty=difficulty,
                    question_type=generated.get("question_type"),
                    is_approved=True,
                    prompt_version="live_interview_v2",
                )
            else:
                raise HTTPException(
                    status_code=503,
                    detail="The AI returned an invalid question source.",
                )

            known_question_query = (
                select(Question.id, Question.question_text).where(
                    Question.id.in_([uuid.UUID(item) for item in order])
                )
                if order
                else None
            )
            known_questions = (
                (await db.execute(known_question_query)).all()
                if known_question_query is not None
                else []
            )
            if any(
                text.strip().casefold() == next_question.question_text.strip().casefold()
                and existing_id != next_question.id
                for existing_id, text in known_questions
            ):
                raise HTTPException(
                    status_code=503,
                    detail="The AI selected a repeated question. Please retry your answer.",
                )
            if not acknowledgement or len(acknowledgement.strip()) < 5:
                acknowledgement = ConversationalService.get_empathetic_acknowledgement(
                    evaluation["fused_score"], transcript
                )
            transition = ConversationalService.get_conversational_transition(
                prev_difficulty=question.difficulty.value if question.difficulty else "medium",
                next_difficulty=next_question.difficulty.value
                if next_question and next_question.difficulty
                else "medium",
                is_same_topic=(question.topic_id == next_question.topic_id)
                if next_question
                else False,
                score=evaluation["fused_score"],
            )
            interviewer_text = f"{acknowledgement.strip()} {transition.strip()} {next_text}".strip()
            updated_config = dict(session.config or {})
            updated_config["follow_up_depth"] = (
                follow_up_depth + 1 if action == "ask_follow_up" else 0
            )
            updated_config["last_decision_reason"] = str(generated.get("reason", ""))[:300]
            if is_adaptive and next_question:
                prog = list(updated_config.get("difficulty_progression", []))
                prog.append(next_question.difficulty.value)
                updated_config["difficulty_progression"] = prog
                t_practiced = list(updated_config.get("topics_practiced", []))
                if next_question.topic_id and str(next_question.topic_id) in topic_by_id:
                    t_name = topic_by_id[str(next_question.topic_id)].name
                    if t_name not in t_practiced:
                        t_practiced.append(t_name)
                updated_config["topics_practiced"] = t_practiced
            session.config = updated_config

    existing_answers = await db.execute(select(Answer.id).where(Answer.session_id == session_id))
    answer = Answer(
        session_id=session_id,
        question_id=question.id,
        sequence_number=len(existing_answers.scalars().all()) + 1,
        transcript=transcript,
        embedding_score=evaluation["embedding_score"],
        llm_score=evaluation["llm_score"],
        fused_score=evaluation["fused_score"],
        rubric_breakdown=evaluation["rubric"],
        llm_raw_response=evaluation["rubric"],
        is_followup=bool(not is_last_question and action == "ask_follow_up"),
    )
    question.times_used += 1
    db.add(answer)
    if next_question is not None:
        if next_question.id is None:
            db.add(next_question)
            await db.flush()
        updated_order = list(order)
        if question_source == "question_bank":
            updated_order.remove(str(next_question.id))
        updated_order.insert(session.current_question_index, str(next_question.id))
        updated_config = dict(session.config or {})
        updated_config["question_order"] = updated_order
        session.config = updated_config
        session.current_question_index += 1
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This answer was already submitted for the current interview question.",
        ) from exc
    await db.refresh(answer)

    completed = next_question is None
    if completed:
        summary = await VivaOrchestrator(db).finish_session(session_id)
        interviewer_text = ConversationalService.get_session_closing_message(
            summary["total_score"] if summary else None,
            current_user.full_name,
            len(existing_answers.scalars().all()) + 1,
        )
    else:
        summary = None
    return {
        "answer_id": str(answer.id),
        "question_id": str(question.id),
        "transcript": transcript,
        "embedding_score": evaluation["embedding_score"],
        "llm_score": evaluation["llm_score"],
        "fused_score": evaluation["fused_score"],
        "rubric_breakdown": evaluation["rubric"],
        "interviewer_text": interviewer_text,
        "next_question": (
            {
                "question_id": str(next_question.id),
                "question_text": next_question.question_text,
                "difficulty": next_question.difficulty.value,
                "topic_id": str(next_question.topic_id),
                "question_source": question_source,
                "is_cross_question": bool(generated.get("is_cross_question"))
                if not is_last_question
                else False,
            }
            if next_question
            else None
        ),
        "completed": completed,
        "total_score": summary["total_score"] if summary else None,
        "adaptive_summary": summary.get("adaptive_summary") if summary else None,
    }


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def start_session(
    payload: VivaStartRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a course-specific session using approved questions, saved syllabus context, or scheduled assignment."""
    assessment = None
    assignment = None

    if payload and payload.assignment_id:
        assignment = await db.scalar(
            select(Assignment)
            .options(
                selectinload(Assignment.assessment),
                selectinload(Assignment.course).selectinload(Course.teacher),
            )
            .where(Assignment.id == payload.assignment_id)
        )
        if assignment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found"
            )
        if not assignment.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This assignment is inactive or closed",
            )

        now = datetime.now(UTC)
        if assignment.start_date:
            st = (
                assignment.start_date
                if assignment.start_date.tzinfo
                else assignment.start_date.replace(tzinfo=UTC)
            )
            if now < st:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This assignment has not started yet",
                )
        if assignment.deadline:
            dl = (
                assignment.deadline
                if assignment.deadline.tzinfo
                else assignment.deadline.replace(tzinfo=UTC)
            )
            if now > dl:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This assignment deadline has passed",
                )

        if current_user.role == UserRole.STUDENT:
            if assignment.assigned_student_ids and str(current_user.id) not in [
                str(x) for x in assignment.assigned_student_ids
            ]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not assigned to this assessment",
                )
            if current_user.institution_id and assignment.course and assignment.course.teacher:
                teacher = assignment.course.teacher
                if teacher.institution_id and teacher.institution_id != current_user.institution_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You cannot access assignments from another institution",
                    )

        # Check existing sessions for this student and assignment
        existing_res = await db.execute(
            select(VivaSession).where(VivaSession.student_id == current_user.id)
        )
        as_id_str = str(assignment.id)
        student_as_sessions = [
            s
            for s in existing_res.scalars().all()
            if (s.config or {}).get("assignment_id") == as_id_str
        ]

        # 409 Conflict if in_progress
        if any(s.status == VivaStatus.IN_PROGRESS for s in student_as_sessions):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already have an active session for this assignment",
            )

        # 403 Forbidden if attempt limit reached
        if len(student_as_sessions) >= assignment.attempt_limit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Maximum attempt limit reached for this assignment",
            )

        course_id = assignment.course_id
        assessment = assignment.assessment
    elif payload and payload.assessment_id:
        assessment = await db.scalar(
            select(Assessment).where(Assessment.id == payload.assessment_id)
        )
        if assessment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found"
            )
        if current_user.role == UserRole.STUDENT and not assessment.is_published:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This assessment is not currently published",
            )
        course_id = assessment.course_id
    elif payload and payload.course_id:
        course_id = payload.course_id
    else:
        latest_course = await db.scalar(select(Course).order_by(Course.created_at.desc()).limit(1))
        course_id = latest_course.id if latest_course else None

    if course_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No courses available for viva sessions"
        )

    course = await db.scalar(select(Course).where(Course.id == course_id))
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    saved_config = course.interview_config or {}
    if assessment:
        max_questions = assessment.max_questions
        max_duration_sec = assessment.duration_minutes * 60
        difficulty = (
            assessment.difficulty
            if assessment.difficulty in ("easy", "medium", "hard")
            else "medium"
        )
        selected_topic_ids = [uuid.UUID(item) for item in assessment.topic_ids if item]
        selected_question_ids = [uuid.UUID(item) for item in assessment.question_ids if item]
    else:
        max_questions = (
            payload.max_questions
            if payload and payload.max_questions is not None
            else saved_config.get("max_questions", 5)
        )
        max_duration_sec = (
            payload.max_duration_sec
            if payload and payload.max_duration_sec is not None
            else saved_config.get("max_duration_sec", 900)
        )
        difficulty = (
            payload.difficulty
            if payload and payload.difficulty is not None
            else saved_config.get("difficulty", "medium")
        )
        selected_topic_ids = (
            payload.topic_ids
            if payload and payload.topic_ids is not None
            else [uuid.UUID(value) for value in saved_config.get("topic_ids", [])]
        )
        selected_question_ids = []

    if selected_topic_ids:
        valid_topic_ids = set(
            (
                await db.execute(
                    select(Topic.id).where(
                        Topic.course_id == course.id,
                        Topic.id.in_(selected_topic_ids),
                    )
                )
            ).scalars()
        )
        if valid_topic_ids != set(selected_topic_ids):
            raise HTTPException(
                status_code=422, detail="Selected topics do not belong to this course"
            )

    orchestrator = VivaOrchestrator(db)
    session = await orchestrator.start_session(
        student_id=current_user.id,
        course_id=course.id,
        config=VivaConfig(
            max_questions=max_questions,
            max_duration_sec=max_duration_sec,
            difficulty=difficulty,
            topic_ids=selected_topic_ids,
            question_ids=selected_question_ids,
        ),
    )
    updated_cfg = dict(session.config or {})
    if assessment or assignment:
        updated_cfg["is_adaptive"] = False
        updated_cfg["practice_mode"] = "fixed"
        if assessment:
            updated_cfg["assessment_id"] = str(assessment.id)
            updated_cfg["assessment_title"] = assessment.title
        if assignment:
            updated_cfg["assignment_id"] = str(assignment.id)
            updated_cfg["assignment_title"] = assignment.title
    else:
        if payload and payload.is_adaptive is not None:
            updated_cfg["is_adaptive"] = payload.is_adaptive
        if payload and payload.practice_mode:
            updated_cfg["practice_mode"] = payload.practice_mode
    session.config = updated_cfg
    await db.commit()

    return {
        "id": session.id,
        "student_id": current_user.id,
        "course_id": course.id,
        "assessment_id": str(assessment.id) if assessment else None,
        "assessment_title": assessment.title if assessment else None,
        "assignment_id": str(assignment.id) if assignment else None,
        "assignment_title": assignment.title if assignment else None,
        "status": session.status.value,
        "is_adaptive": (session.config or {}).get("is_adaptive", False),
        "practice_mode": (session.config or {}).get("practice_mode", "standard"),
        "max_questions": session.max_questions,
        "current_question_index": session.current_question_index,
        "started_at": session.started_at,
    }


@router.get("/sessions", status_code=status.HTTP_200_OK)
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List viva sessions for the current user."""
    result = await db.execute(
        select(VivaSession)
        .options(selectinload(VivaSession.course))
        .where(VivaSession.student_id == current_user.id)
        .order_by(VivaSession.created_at.desc())
    )
    sessions = result.scalars().all()
    return [
        {
            "id": session.id,
            "student_id": session.student_id,
            "course_id": session.course_id,
            "course_name": session.course.name if session.course else None,
            "course_code": session.course.code if session.course else None,
            "assessment_id": (session.config or {}).get("assessment_id"),
            "assessment_title": (session.config or {}).get("assessment_title"),
            "assignment_id": (session.config or {}).get("assignment_id"),
            "assignment_title": (session.config or {}).get("assignment_title"),
            "is_adaptive": (session.config or {}).get("is_adaptive", False),
            "practice_mode": (session.config or {}).get("practice_mode", "standard"),
            "status": session.status.value,
            "max_questions": session.max_questions,
            "current_question_index": session.current_question_index,
            "total_score": session.total_score,
            "started_at": session.started_at,
            "finished_at": session.finished_at,
            "created_at": session.created_at,
        }
        for session in sessions
    ]


@router.get("/insights", status_code=status.HTTP_200_OK)
async def get_student_insights(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Analyze completed viva sessions for weakness detection, strength recognition, and personalized recommendations."""
    result = await db.execute(
        select(VivaSession)
        .options(
            selectinload(VivaSession.course),
            selectinload(VivaSession.answers)
            .selectinload(Answer.question)
            .selectinload(Question.topic)
            .selectinload(Topic.course),
            selectinload(VivaSession.answers).selectinload(Answer.score_override),
        )
        .where(
            VivaSession.student_id == current_user.id,
            VivaSession.status == VivaStatus.COMPLETED,
        )
        .order_by(VivaSession.created_at.desc())
    )
    sessions = result.scalars().unique().all()

    courses_result = await db.execute(
        select(Course).options(selectinload(Course.topics)).order_by(Course.created_at.desc())
    )
    all_courses = courses_result.scalars().unique().all()

    if not sessions:
        initial_recommendations = []
        for course in all_courses:
            for topic in (course.topics or [])[:2]:
                initial_recommendations.append(
                    {
                        "id": f"rec-{topic.id}",
                        "topic_id": str(topic.id),
                        "topic_name": topic.name,
                        "course_id": str(course.id),
                        "course_name": course.name,
                        "course_code": course.code,
                        "priority": "normal",
                        "reason": f"Explore fundamental topics in {course.name} to begin your oral practice.",
                        "start_url": f"/viva/{course.id}?topic={topic.id}",
                    }
                )
                if len(initial_recommendations) >= 3:
                    break
            if len(initial_recommendations) >= 3:
                break

        return {
            "has_data": False,
            "total_evaluated_sessions": 0,
            "total_evaluated_answers": 0,
            "overall_average_score": None,
            "overall_average_score_percent": "—",
            "weaknesses": [],
            "strengths": [],
            "developing": [],
            "recommendations": initial_recommendations,
            "message": "Complete at least one viva session to generate AI-powered weakness detection and personalized recommendations.",
            "coaching_note": "Choose any available course topic below to begin your first practice oral exam.",
        }

    topic_map: dict[uuid.UUID, dict[str, Any]] = {}
    total_answers = 0
    all_scores: list[float] = []

    for session in sessions:
        for answer in session.answers:
            if not answer.question or not answer.question.topic:
                continue

            topic = answer.question.topic
            tid = topic.id

            score = None
            if answer.score_override and answer.score_override.override_score is not None:
                score = float(answer.score_override.override_score)
            elif answer.fused_score is not None:
                score = float(answer.fused_score)
            elif answer.llm_score is not None:
                score = float(answer.llm_score)

            rubric = answer.rubric_breakdown or {}
            c_score = rubric.get("correctness")
            comp_score = rubric.get("completeness")
            clar_score = rubric.get("clarity")
            justification = rubric.get("justification") or ""

            if tid not in topic_map:
                topic_map[tid] = {
                    "topic_id": str(tid),
                    "topic_name": topic.name,
                    "course_id": str(topic.course_id),
                    "course_name": topic.course.name
                    if topic.course
                    else (session.course.name if session.course else ""),
                    "course_code": topic.course.code
                    if topic.course
                    else (session.course.code if session.course else ""),
                    "scores": [],
                    "correctness_scores": [],
                    "completeness_scores": [],
                    "clarity_scores": [],
                    "feedback_snippets": [],
                    "answers_count": 0,
                }

            topic_map[tid]["answers_count"] += 1
            total_answers += 1

            if score is not None:
                topic_map[tid]["scores"].append(score)
                all_scores.append(score)

            if isinstance(c_score, (int, float)):
                topic_map[tid]["correctness_scores"].append(float(c_score))
            if isinstance(comp_score, (int, float)):
                topic_map[tid]["completeness_scores"].append(float(comp_score))
            if isinstance(clar_score, (int, float)):
                topic_map[tid]["clarity_scores"].append(float(clar_score))

            if justification and len(justification.strip()) > 10:
                clean_just = justification.strip().split("\n")[0]
                if len(clean_just) > 160:
                    clean_just = clean_just[:157] + "..."
                if (
                    clean_just not in topic_map[tid]["feedback_snippets"]
                    and len(topic_map[tid]["feedback_snippets"]) < 3
                ):
                    topic_map[tid]["feedback_snippets"].append(clean_just)

    overall_avg = round(sum(all_scores) / len(all_scores), 4) if all_scores else None
    overall_avg_pct = f"{round(overall_avg * 100)}%" if overall_avg is not None else "—"

    weaknesses = []
    strengths = []
    developing = []

    for tdata in topic_map.values():
        scores = tdata["scores"]
        if not scores:
            continue

        avg_score = round(sum(scores) / len(scores), 4)
        avg_score_pct = f"{round(avg_score * 100)}%"

        avg_corr = (
            round(sum(tdata["correctness_scores"]) / len(tdata["correctness_scores"]), 1)
            if tdata["correctness_scores"]
            else None
        )
        avg_comp = (
            round(sum(tdata["completeness_scores"]) / len(tdata["completeness_scores"]), 1)
            if tdata["completeness_scores"]
            else None
        )
        avg_clar = (
            round(sum(tdata["clarity_scores"]) / len(tdata["clarity_scores"]), 1)
            if tdata["clarity_scores"]
            else None
        )

        primary_gap = "general"
        if avg_comp is not None and avg_corr is not None:
            if avg_comp < avg_corr and avg_comp < 6.0:
                primary_gap = "completeness (missing key concepts)"
            elif avg_corr < avg_comp and avg_corr < 6.0:
                primary_gap = "conceptual accuracy"
            elif avg_clar is not None and avg_clar < 6.0:
                primary_gap = "clarity and verbal structure"

        feedback_themes = list(tdata["feedback_snippets"])
        if not feedback_themes:
            if avg_score < 0.65:
                feedback_themes.append(
                    f"Average score of {avg_score_pct} indicates conceptual gaps in oral responses."
                )
            elif avg_score >= 0.80:
                feedback_themes.append(
                    f"Strong performance ({avg_score_pct}) with consistent accuracy across questions."
                )

        topic_insight = {
            "topic_id": tdata["topic_id"],
            "topic_name": tdata["topic_name"],
            "course_id": tdata["course_id"],
            "course_name": tdata["course_name"],
            "course_code": tdata["course_code"],
            "average_score": avg_score,
            "average_score_percent": avg_score_pct,
            "evaluated_answers_count": len(scores),
            "dimension_scores": {
                "correctness": avg_corr,
                "completeness": avg_comp,
                "clarity": avg_clar,
            },
            "feedback_themes": feedback_themes,
            "primary_gap": primary_gap,
        }

        if avg_score < 0.65:
            topic_insight["status"] = "weakness"
            weaknesses.append(topic_insight)
        elif avg_score >= 0.80:
            topic_insight["status"] = "strength"
            strengths.append(topic_insight)
        else:
            topic_insight["status"] = "developing"
            developing.append(topic_insight)

    weaknesses.sort(key=lambda x: x["average_score"])
    strengths.sort(key=lambda x: x["average_score"], reverse=True)
    developing.sort(key=lambda x: x["average_score"])

    recommendations = []
    for w in weaknesses:
        recommendations.append(
            {
                "id": f"rec-weak-{w['topic_id']}",
                "topic_id": w["topic_id"],
                "topic_name": w["topic_name"],
                "course_id": w["course_id"],
                "course_name": w["course_name"],
                "course_code": w["course_code"],
                "priority": "high",
                "reason": f"Scored {w['average_score_percent']} across {w['evaluated_answers_count']} questions. Primary gap: {w['primary_gap']}.",
                "start_url": f"/viva/{w['course_id']}?topic={w['topic_id']}",
            }
        )

    for d in developing:
        if len(recommendations) >= 4:
            break
        recommendations.append(
            {
                "id": f"rec-dev-{d['topic_id']}",
                "topic_id": d["topic_id"],
                "topic_name": d["topic_name"],
                "course_id": d["course_id"],
                "course_name": d["course_name"],
                "course_code": d["course_code"],
                "priority": "medium",
                "reason": f"Scored {d['average_score_percent']}. Reinforce key principles to reach mastery.",
                "start_url": f"/viva/{d['course_id']}?topic={d['topic_id']}",
            }
        )

    tested_topic_ids = set(topic_map.keys())
    for course in all_courses:
        if len(recommendations) >= 4:
            break
        for topic in course.topics or []:
            if topic.id not in tested_topic_ids:
                recommendations.append(
                    {
                        "id": f"rec-new-{topic.id}",
                        "topic_id": str(topic.id),
                        "topic_name": topic.name,
                        "course_id": str(course.id),
                        "course_name": course.name,
                        "course_code": course.code,
                        "priority": "normal",
                        "reason": f"New topic in {course.name}. Practice early to assess comprehension.",
                        "start_url": f"/viva/{course.id}?topic={topic.id}",
                    }
                )
                if len(recommendations) >= 4:
                    break

    has_evaluated_data = bool(all_scores)

    if not has_evaluated_data:
        coaching_note = (
            "Choose any available course topic below to begin your first practice oral exam."
        )
    elif weaknesses:
        top_weak = weaknesses[0]
        coaching_note = (
            f"Focus your next practice on '{top_weak['topic_name']}' ({top_weak['average_score_percent']}). "
            f"Address {top_weak['primary_gap']} by structuring answers around key technical definitions."
        )
    elif developing:
        top_dev = developing[0]
        coaching_note = (
            f"You are progressing well! Level up your '{top_dev['topic_name']}' performance ({top_dev['average_score_percent']}) "
            "into the mastery tier with more comprehensive examples."
        )
    else:
        coaching_note = "Outstanding performance across all evaluated topics! Continue regular viva sessions to maintain conversational agility."

    return {
        "has_data": has_evaluated_data,
        "total_evaluated_sessions": len(sessions) if has_evaluated_data else 0,
        "total_evaluated_answers": len(all_scores),
        "overall_average_score": overall_avg,
        "overall_average_score_percent": overall_avg_pct,
        "weaknesses": weaknesses,
        "strengths": strengths,
        "developing": developing,
        "recommendations": recommendations,
        "coaching_note": coaching_note,
    }


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return a viva session summary for the current user."""
    result = await db.execute(select(VivaSession).where(VivaSession.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.student_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this session"
        )

    return {
        "id": session.id,
        "student_id": session.student_id,
        "course_id": session.course_id,
        "status": session.status.value,
        "max_questions": session.max_questions,
        "current_question_index": session.current_question_index,
        "started_at": session.started_at,
        "finished_at": session.finished_at,
    }


@router.post("/sessions/{session_id}/behavior-flags", status_code=status.HTTP_201_CREATED)
async def create_behavior_flag(
    session_id: uuid.UUID,
    payload: BehaviorFlagCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Persist only a cue type and timestamp, never camera frames."""
    result = await db.execute(select(VivaSession).where(VivaSession.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="You do not have access to this session")
    consent_result = await db.execute(
        select(Consent).where(
            Consent.user_id == current_user.id,
            Consent.session_id == session_id,
            Consent.camera_analysis_consent.is_(True),
            Consent.revoked_at.is_(None),
        )
    )
    if consent_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Camera cue analysis consent is required")

    flags = list((session.config or {}).get("behavior_flags", []))
    if len(flags) >= 100:
        raise HTTPException(status_code=429, detail="Session review cue limit reached")
    flag = {"cue_type": payload.cue_type, "occurred_at": datetime.now(UTC).isoformat()}
    updated_config = dict(session.config or {})
    updated_config["behavior_flags"] = [*flags, flag]
    session.config = updated_config
    await db.commit()
    return flag


@router.post("/sessions/{session_id}/next")
async def next_question(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return the next question in the viva session or finalize it when all questions are consumed."""
    orchestrator = VivaOrchestrator(db)
    session = await orchestrator._get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.student_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this session",
        )

    try:
        question = await orchestrator.get_next_question(session_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if question is None:
        summary = await orchestrator.finish_session(session_id)
        return {
            "session_id": str(session_id),
            "status": summary["status"],
            "message": "Session completed; no further questions available.",
            "total_score": summary["total_score"],
        }

    refreshed_session = await orchestrator._get_session(session_id)
    opening_greeting = None
    if refreshed_session and refreshed_session.current_question_index == 1:
        cfg = refreshed_session.config or {}
        is_adapt = AdaptiveVivaService.is_adaptive_session(refreshed_session)
        asst_title = cfg.get("assessment_title") or cfg.get("assignment_title")
        opening_greeting = ConversationalService.get_viva_opening(
            current_user.full_name, is_adapt, asst_title
        )

    return {
        "session_id": str(session_id),
        "question_id": str(question.id),
        "question_text": question.question_text,
        "opening_greeting": opening_greeting,
        "expected_key_points": question.expected_key_points,
        "difficulty": question.difficulty.value,
        "current_question_index": refreshed_session.current_question_index
        if refreshed_session
        else 0,
    }


@router.post("/sessions/{session_id}/turn")
async def submit_interview_turn(
    session_id: uuid.UUID,
    payload: InterviewTurnRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Accept a browser's finalized live transcript and return the next AI turn."""
    return await _process_interview_turn(session_id, payload, current_user, db)


@router.post("/sessions/{session_id}/turn/audio")
async def submit_interview_audio_turn(
    session_id: uuid.UUID,
    file: UploadFile = File(...),
    question_id: uuid.UUID = Form(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Transcribe an automatically captured utterance when browser captions are unavailable."""
    session = await db.scalar(select(VivaSession).where(VivaSession.id == session_id))
    if session is None:
        raise HTTPException(status_code=404, detail="Interview session not found")
    if session.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="You do not have access to this interview")
    if session.status.value != "in_progress":
        raise HTTPException(status_code=409, detail="This interview is no longer in progress")

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="The recorded answer is empty.")
    if len(raw_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="The recorded answer exceeds the 20 MB limit.")

    stored_path = SpeechService.save_audio_upload(raw_bytes, session_id, current_user.id)
    try:
        transcription = await run_in_threadpool(SpeechService().transcribe, stored_path)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        Path(stored_path).unlink(missing_ok=True)
        Path(stored_path).with_suffix(".wav").unlink(missing_ok=True)

    payload = InterviewTurnRequest(
        question_id=question_id, transcript=transcription.get("text", "")
    )
    return await _process_interview_turn(session_id, payload, current_user, db)


@router.post("/sessions/{session_id}/answer")
async def submit_answer(
    session_id: uuid.UUID,
    file: UploadFile = File(...),
    question_id: uuid.UUID | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Accept an uploaded audio answer, transcript it, and store the cleaned result."""
    session_result = await db.execute(select(VivaSession).where(VivaSession.id == session_id))
    session = session_result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.student_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only answer your own viva session",
        )

    if question_id is None:
        question_result = await db.execute(
            select(Question)
            .join(Topic, Question.topic_id == Topic.id)
            .where(Topic.course_id == session.course_id)
            .order_by(Question.created_at.desc())
            .limit(1)
        )
        question = question_result.scalar_one_or_none()
        if question is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No question available for this session",
            )
    else:
        question_result = await db.execute(select(Question).where(Question.id == question_id))
        question = question_result.scalar_one_or_none()
        if question is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")

    consent_result = await db.execute(
        select(Consent)
        .where(Consent.user_id == current_user.id, Consent.audio_retention_consent.is_(True))
        .order_by(Consent.consented_at.desc())
        .limit(1)
    )
    consent = consent_result.scalar_one_or_none()
    has_consent = (
        consent is not None
        and consent.audio_retention_consent is True
        and consent.revoked_at is None
    )

    try:
        raw_bytes = await file.read()
    except Exception as exc:  # pragma: no cover - file read failure path
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to read uploaded audio file"
        ) from exc

    if not raw_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded audio is empty"
        )

    settings = get_settings()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(raw_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Uploaded audio file exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB",
        )

    started = time.perf_counter()
    stored_path = SpeechService.save_audio_upload(raw_bytes, session_id, current_user.id)
    try:
        transcription = SpeechService().transcribe(stored_path)
    except RuntimeError as exc:
        if Path(stored_path).exists():
            Path(stored_path).unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    transcript = clean_transcript(transcription.get("text", ""))
    transcript = anonymise(transcript)
    try:
        evaluation = await evaluate_answer(
            question=question.question_text,
            transcript=transcript,
            key_points=question.expected_key_points,
        )
    except RuntimeError as exc:
        if not has_consent and Path(stored_path).exists():
            Path(stored_path).unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    audio_path = stored_path if has_consent else None
    if not has_consent and Path(stored_path).exists():
        Path(stored_path).unlink(missing_ok=True)

    existing_answers_result = await db.execute(
        select(Answer).where(Answer.session_id == session_id)
    )
    next_sequence = len(existing_answers_result.scalars().all()) + 1

    answer = Answer(
        session_id=session_id,
        question_id=question.id,
        sequence_number=next_sequence,
        transcript=transcript,
        embedding_score=evaluation["embedding_score"],
        llm_score=evaluation["llm_score"],
        fused_score=evaluation["fused_score"],
        rubric_breakdown=evaluation["rubric"],
        llm_raw_response=evaluation["rubric"],
        audio_path=audio_path,
        transcription_confidence=transcription.get("confidence"),
        latency_ms=elapsed_ms,
    )
    db.add(answer)
    await db.commit()
    await db.refresh(answer)

    followup = None
    followup_error = None
    threshold = float((session.config or {}).get("follow_up_threshold", 0.4))
    if (
        evaluation["fused_score"] < threshold
        and session.current_question_index < session.max_questions
    ):
        try:
            followup = await VivaOrchestrator(db).generate_followup(
                session_id,
                missed_key_points=question.expected_key_points,
                previous_question=question.question_text,
                transcript=transcript,
            )
        except RuntimeError as exc:
            followup_error = f"Adaptive follow-up unavailable: {exc}"

    return {
        "answer_id": answer.id,
        "transcript": transcript,
        "embedding_score": evaluation["embedding_score"],
        "llm_score": evaluation["llm_score"],
        "fused_score": evaluation["fused_score"],
        "rubric_breakdown": evaluation["rubric"],
        "audio_saved": bool(audio_path),
        "audio_path": audio_path,
        "confidence": transcription.get("confidence"),
        "latency_ms": elapsed_ms,
        "followup": (
            {
                "question_id": str(followup.id),
                "question_text": followup.question_text,
                "expected_key_points": followup.expected_key_points,
                "difficulty": followup.difficulty.value,
            }
            if followup
            else None
        ),
        "followup_error": followup_error,
    }


@router.post("/sessions/{session_id}/finish")
async def finish_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Finalize a viva session and compute the aggregate score for all recorded answers."""
    orchestrator = VivaOrchestrator(db)
    session = await orchestrator._get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.student_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this session",
        )

    summary = await orchestrator.finish_session(session_id)
    return {
        "session_id": str(session_id),
        "status": summary["status"],
        "total_score": summary["total_score"],
        "answers_count": summary["answers_count"],
        "finished_at": summary["finished_at"],
    }


@router.get("/sessions/{session_id}/adaptive-summary", status_code=status.HTTP_200_OK)
async def get_adaptive_session_summary(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve the adaptive learning summary for a viva session."""
    session_res = await db.execute(
        select(VivaSession)
        .options(selectinload(VivaSession.course))
        .where(VivaSession.id == session_id)
    )
    session = session_res.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if current_user.role == UserRole.STUDENT and session.student_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You do not have access to this session summary"
        )
    if (
        current_user.role == UserRole.TEACHER
        and session.course
        and session.course.teacher_id != current_user.id
    ):
        raise HTTPException(
            status_code=403, detail="You do not have access to this session summary"
        )

    summary = (session.config or {}).get("adaptive_summary")
    if not summary:
        if AdaptiveVivaService.is_adaptive_session(session):
            summary = await AdaptiveVivaService.generate_session_summary(db, session)
        else:
            return {
                "is_adaptive": False,
                "session_id": str(session.id),
                "message": "This was a fixed assessment or assignment session.",
            }

    return summary
