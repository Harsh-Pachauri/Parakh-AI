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

from app.api.deps import get_current_user, get_db
from app.models.answer import Answer
from app.models.consent import Consent
from app.models.course import Course
from app.models.question import Question, QuestionDifficulty
from app.models.topic import Topic
from app.models.user import User
from app.models.viva_session import VivaSession
from app.schemas.viva import (
    BehaviorFlagCreate,
    InterviewTurnRequest,
    VivaConfig,
    VivaStartRequest,
)
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

    try:
        evaluation = await evaluate_answer(
            question=question.question_text,
            transcript=transcript,
            key_points=question.expected_key_points,
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
        history = [
            f"Interviewer: {answered_question.question_text[:300]}\n"
            f"Candidate: {(answer.transcript or '')[-600:]}"
            for answer, answered_question in history_result.all()
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
                    raise HTTPException(
                        status_code=503,
                        detail="The AI selected a question outside the retrieved question bank.",
                    )
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
            interviewer_text = f"{acknowledgement.strip()} {next_text}".strip()
            updated_config = dict(session.config or {})
            updated_config["follow_up_depth"] = (
                follow_up_depth + 1 if action == "ask_follow_up" else 0
            )
            updated_config["last_decision_reason"] = str(generated.get("reason", ""))[:300]
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
    }


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def start_session(
    payload: VivaStartRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a course-specific session using approved questions or saved syllabus context."""
    result = await db.execute(
        select(Course).where(Course.id == payload.course_id)
        if payload
        else select(Course).order_by(Course.created_at.desc()).limit(1)
    )
    course = result.scalar_one_or_none()
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No courses available for viva sessions"
        )

    saved_config = course.interview_config or {}
    selected_topic_ids = (
        payload.topic_ids
        if payload and payload.topic_ids is not None
        else [uuid.UUID(value) for value in saved_config.get("topic_ids", [])]
    )
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
            max_questions=(
                payload.max_questions
                if payload and payload.max_questions is not None
                else saved_config.get("max_questions", 5)
            ),
            max_duration_sec=(
                payload.max_duration_sec
                if payload and payload.max_duration_sec is not None
                else saved_config.get("max_duration_sec", 900)
            ),
            difficulty=(
                payload.difficulty
                if payload and payload.difficulty is not None
                else saved_config.get("difficulty", "medium")
            ),
            topic_ids=selected_topic_ids,
        ),
    )
    return {
        "id": session.id,
        "student_id": current_user.id,
        "course_id": course.id,
        "status": session.status.value,
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
        .where(VivaSession.student_id == current_user.id)
        .order_by(VivaSession.created_at.desc())
    )
    sessions = result.scalars().all()
    return [
        {
            "id": session.id,
            "student_id": session.student_id,
            "course_id": session.course_id,
            "status": session.status.value,
            "max_questions": session.max_questions,
            "current_question_index": session.current_question_index,
            "started_at": session.started_at,
        }
        for session in sessions
    ]


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
    return {
        "session_id": str(session_id),
        "question_id": str(question.id),
        "question_text": question.question_text,
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
