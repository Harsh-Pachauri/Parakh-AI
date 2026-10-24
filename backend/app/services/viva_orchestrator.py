"""State-machine orchestration for viva sessions."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answer import Answer
from app.models.course import Course
from app.models.question import Question, QuestionDifficulty
from app.models.topic import Topic
from app.models.viva_session import VivaSession, VivaStatus
from app.schemas.viva import VivaConfig
from app.services.adaptive_service import AdaptiveVivaService
from app.services.eval_service import evaluate_answer
from app.services.llm_service import get_provider
from app.services.speech_service import SpeechService
from app.utils.text import anonymise, clean_transcript


class VivaOrchestrator:
    """Manage the question flow and scoring lifecycle for a viva session."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _get_session(self, session_id: uuid.UUID) -> VivaSession | None:
        result = await self.db.execute(select(VivaSession).where(VivaSession.id == session_id))
        return result.scalar_one_or_none()

    async def _course_question_ids(
        self,
        course_id: uuid.UUID,
        difficulty: str | None = None,
        topic_ids: list[str] | None = None,
    ) -> list[uuid.UUID]:
        statement = (
            select(Question.id)
            .join(Topic, Question.topic_id == Topic.id)
            .where(Topic.course_id == course_id, Question.is_approved.is_(True))
        )
        if difficulty:
            statement = statement.where(Question.difficulty == QuestionDifficulty(difficulty))
        if topic_ids:
            statement = statement.where(Topic.id.in_([uuid.UUID(item) for item in topic_ids]))
        result = await self.db.execute(
            statement.order_by(Question.times_used.asc(), Question.created_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    def _question_sort_key(question_id: uuid.UUID) -> tuple[int, datetime, uuid.UUID]:
        return (0, datetime.min.replace(tzinfo=UTC), question_id)

    async def _ensure_question_order(self, session: VivaSession) -> list[uuid.UUID]:
        question_order = [
            uuid.UUID(value) for value in session.config.get("question_order", []) if value
        ]
        if question_order:
            return question_order

        config = session.config or {}
        course_question_ids = await self._course_question_ids(
            session.course_id,
            config.get("difficulty"),
            config.get("topic_ids"),
        )
        session.config["question_order"] = [str(item) for item in course_question_ids]
        await self.db.commit()
        return course_question_ids

    async def start_session(
        self,
        student_id: uuid.UUID,
        course_id: uuid.UUID,
        config: VivaConfig | None = None,
    ) -> VivaSession:
        """Create a viva session and cache the initial order of reusable questions."""
        viva_config = config or VivaConfig()
        topic_ids = [str(item) for item in viva_config.topic_ids]
        is_fixed = bool(viva_config.question_ids)
        if is_fixed:
            question_order = [uuid.UUID(str(item)) for item in viva_config.question_ids]
            is_adaptive = False
            practice_mode = "fixed"
        else:
            question_order = await self._course_question_ids(
                course_id, viva_config.difficulty, topic_ids
            )
            is_adaptive = True
            practice_mode = "targeted" if len(topic_ids) == 1 else "adaptive"

        session = VivaSession(
            student_id=student_id,
            course_id=course_id,
            status=VivaStatus.IN_PROGRESS,
            max_questions=viva_config.max_questions,
            max_duration_sec=viva_config.max_duration_sec,
            current_question_index=0,
            started_at=datetime.now(UTC),
            config={
                "question_order": [str(item) for item in question_order],
                "max_questions": viva_config.max_questions,
                "max_duration_sec": viva_config.max_duration_sec,
                "follow_up_threshold": viva_config.follow_up_threshold,
                "difficulty": viva_config.difficulty,
                "topic_ids": topic_ids,
                "is_adaptive": is_adaptive,
                "practice_mode": practice_mode,
                "difficulty_progression": [],
                "topics_practiced": [],
                "asked_question_ids": [],
                "topic_coverage": {},
                "follow_up_depth": 0,
            },
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get_next_question(self, session_id: uuid.UUID) -> Question | None:
        """Return the next question for a session or auto-finish when the limit is reached."""
        session = await self._get_session(session_id)
        if session is None:
            raise ValueError("Session not found")

        if session.status == VivaStatus.COMPLETED:
            return None

        if session.current_question_index >= session.max_questions:
            await self.finish_session(session_id)
            return None

        # Adaptive session path: dynamic question selection based on student performance
        if AdaptiveVivaService.is_adaptive_session(session):
            question = await AdaptiveVivaService.get_next_adaptive_question(self.db, session)
            if question is None:
                # Check if question_order has an unasked question before syllabus generation
                question_order = [
                    uuid.UUID(value)
                    for value in (session.config or {}).get("question_order", [])
                    if value
                ]
                asked = set((session.config or {}).get("asked_question_ids", []))
                for qid in question_order:
                    if str(qid) not in asked:
                        q_res = await self.db.execute(select(Question).where(Question.id == qid))
                        q_obj = q_res.scalar_one_or_none()
                        if q_obj:
                            question = q_obj
                            break

            if question is None:
                question = await self._generate_initial_question(session)
                if question is not None:
                    self.db.add(question)
                    await self.db.flush()
            if question is None:
                await self.finish_session(session_id)
                return None

            session.current_question_index += 1
            config = dict(session.config or {})
            asked_ids = list(config.get("asked_question_ids", []))
            if str(question.id) not in asked_ids:
                asked_ids.append(str(question.id))
            config["asked_question_ids"] = asked_ids
            coverage = dict(config.get("topic_coverage", {}))
            coverage[str(question.topic_id)] = "in_progress"
            config["topic_coverage"] = coverage
            session.config = config
            await self.db.commit()
            await self.db.refresh(session)
            return question

        # Fixed session path (assessments, assignments, or explicit question orders)
        question_order = await self._ensure_question_order(session)
        if not question_order:
            question = await self._generate_initial_question(session)
            if question is None:
                await self.finish_session(session_id)
                return None
            self.db.add(question)
            await self.db.flush()
            question_order = [question.id]
            config = dict(session.config or {})
            config["question_order"] = [str(question.id)]
            session.config = config
            await self.db.commit()

        if session.current_question_index >= len(question_order):
            await self.finish_session(session_id)
            return None

        question_id = question_order[session.current_question_index]
        question_result = await self.db.execute(select(Question).where(Question.id == question_id))
        question = question_result.scalar_one_or_none()
        if question is None:
            await self.finish_session(session_id)
            return None

        session.current_question_index += 1
        config = dict(session.config or {})
        asked_ids = list(config.get("asked_question_ids", []))
        asked_ids.append(str(question.id))
        config["asked_question_ids"] = asked_ids
        coverage = dict(config.get("topic_coverage", {}))
        coverage[str(question.topic_id)] = "in_progress"
        config["topic_coverage"] = coverage
        session.config = config
        await self.db.commit()
        await self.db.refresh(session)
        return question

    async def _generate_initial_question(self, session: VivaSession) -> Question | None:
        """Create the first question from saved syllabus context when no approved bank item fits."""
        course = await self.db.scalar(select(Course).where(Course.id == session.course_id))
        if course is None:
            raise RuntimeError("Interview course could not be loaded.")
        if not course.syllabus_text and not course.syllabus_analysis:
            raise RuntimeError(
                "This course has no saved syllabus. Ask the teacher to add and analyze it first."
            )
        allowed_topics = list((session.config or {}).get("topic_ids", []))
        topic_query = select(Topic).where(Topic.course_id == course.id)
        if allowed_topics:
            topic_query = topic_query.where(
                Topic.id.in_([uuid.UUID(item) for item in allowed_topics])
            )
        topic = await self.db.scalar(topic_query.order_by(Topic.sort_order).limit(1))
        if topic is None:
            raise RuntimeError("The selected course has no syllabus topics to interview on.")

        syllabus_topics = []
        source_excerpts = []
        analysis = course.syllabus_analysis or {}
        for module in analysis.get("modules", []):
            for item in module.get("topics", []):
                if item.get("name", "").casefold() == topic.name.casefold():
                    syllabus_topics.append({"module": module.get("name"), **item})
                    for reference in item.get("source_references", [])[:2]:
                        start = reference.get("start")
                        end = reference.get("end")
                        if course.syllabus_text and isinstance(start, int) and isinstance(end, int):
                            source_excerpts.append(course.syllabus_text[start:end][:4000])
        context = {
            "course": course.name,
            "subject": course.subject or course.code,
            "academic_level": course.academic_level,
            "description": course.description,
            "syllabus_topics": syllabus_topics,
            "source_excerpts": source_excerpts,
            "topic": topic.name,
            "source_excerpt": (
                (course.syllabus_text or "")[:5000]
                if not syllabus_topics and course.syllabus_text
                else None
            ),
        }
        schema = {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "key_points": {"type": "array", "items": {"type": "string"}},
                "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
            },
            "required": ["question", "key_points", "difficulty"],
            "additionalProperties": False,
        }
        prompt = (
            "Create one oral interview question grounded only in the saved syllabus context. "
            "Do not add facts or topics not present in it. Return a concise question and specific "
            "expected answer concepts as JSON. If a difficulty is configured, use it.\n"
            f"Configured difficulty: {(session.config or {}).get('difficulty') or 'adaptive'}\n"
            f"Context: {json.dumps(context, ensure_ascii=False)}"
        )
        response = await get_provider().generate(prompt, schema=schema)
        if not isinstance(response, dict):
            raise RuntimeError("Groq returned an invalid initial question.")
        question_text = response.get("question")
        key_points = response.get("key_points")
        if (
            not isinstance(question_text, str)
            or not question_text.strip()
            or not isinstance(key_points, list)
            or not key_points
            or any(not isinstance(point, str) for point in key_points)
        ):
            raise RuntimeError("Groq returned an incomplete initial question.")
        try:
            difficulty = QuestionDifficulty(response.get("difficulty", "medium"))
        except ValueError as exc:
            raise RuntimeError("Groq returned an invalid initial question difficulty.") from exc
        return Question(
            topic_id=topic.id,
            question_text=question_text.strip(),
            expected_key_points=[point.strip() for point in key_points if point.strip()],
            difficulty=difficulty,
            is_approved=True,
            generated_by=None,
            prompt_version="syllabus_interview_v1",
        )

    async def finish_session(self, session_id: uuid.UUID) -> dict[str, Any]:
        """Compute the final weighted score and mark the session complete."""
        session = await self._get_session(session_id)
        if session is None:
            raise ValueError("Session not found")

        answers_result = await self.db.execute(
            select(Answer).where(Answer.session_id == session_id).order_by(Answer.sequence_number)
        )
        answers = list(answers_result.scalars().all())

        if answers:
            scores = [
                answer.fused_score
                if answer.fused_score is not None
                else (
                    answer.llm_score
                    if answer.llm_score is not None
                    else answer.embedding_score or 0.0
                )
                for answer in answers
            ]
            total_score = sum(scores) / len(scores)
        else:
            total_score = 0.0

        session.total_score = round(float(total_score), 4)
        session.status = VivaStatus.COMPLETED
        session.finished_at = datetime.now(UTC)
        session.current_question_index = max(session.current_question_index, len(answers))

        adaptive_summary = None
        if AdaptiveVivaService.is_adaptive_session(session):
            adaptive_summary = await AdaptiveVivaService.generate_session_summary(self.db, session)

        await self.db.commit()
        await self.db.refresh(session)

        return {
            "session_id": str(session.id),
            "status": session.status.value,
            "total_score": session.total_score,
            "answers_count": len(answers),
            "finished_at": session.finished_at,
            "adaptive_summary": adaptive_summary,
        }

    async def process_answer(
        self,
        session_id: uuid.UUID,
        audio_file: Any,
        question_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Process an uploaded answer, transcribe it, score it, and persist the record."""
        session = await self._get_session(session_id)
        if session is None:
            raise ValueError("Session not found")

        if question_id is None:
            question_ids = await self._ensure_question_order(session)
            next_index = min(session.current_question_index, max(len(question_ids) - 1, 0))
            if next_index < len(question_ids):
                chosen_question_id = question_ids[next_index]
            else:
                chosen_question_id = None
        else:
            chosen_question_id = question_id

        if chosen_question_id is None:
            raise ValueError("No available question for this session")

        question_result = await self.db.execute(
            select(Question).where(Question.id == chosen_question_id)
        )
        question = question_result.scalar_one_or_none()
        if question is None:
            raise ValueError("Question not found")

        raw_bytes = await audio_file.read()
        if not raw_bytes:
            raise ValueError("Uploaded audio is empty")

        if user_id is None:
            user_id = session.student_id

        stored_path = SpeechService.save_audio_upload(raw_bytes, session_id, user_id)
        transcription = SpeechService().transcribe(stored_path)
        transcript = clean_transcript(transcription.get("text", ""))
        transcript = anonymise(transcript)

        key_points = question.expected_key_points or (
            [question.explanation] if question.explanation else []
        )
        evaluation = await evaluate_answer(
            question=question.question_text,
            transcript=transcript,
            key_points=key_points,
        )

        existing_answers = (
            (await self.db.execute(select(Answer).where(Answer.session_id == session_id)))
            .scalars()
            .all()
        )
        next_sequence = len(existing_answers) + 1
        answer = Answer(
            session_id=session.id,
            question_id=question.id,
            sequence_number=next_sequence,
            transcript=transcript,
            embedding_score=evaluation["embedding_score"],
            llm_score=evaluation["llm_score"],
            fused_score=evaluation["fused_score"],
            rubric_breakdown=evaluation["rubric"],
            llm_raw_response=evaluation["rubric"],
            audio_path=stored_path,
            transcription_confidence=transcription.get("confidence"),
            latency_ms=transcription.get("duration_ms"),
        )
        self.db.add(answer)
        await self.db.commit()
        await self.db.refresh(answer)

        return {
            "answer_id": str(answer.id),
            "question_id": str(question.id),
            "transcript": transcript,
            "confidence": transcription.get("confidence"),
            "fused_score": evaluation["fused_score"],
            "rubric": evaluation["rubric"],
        }

    async def generate_followup(
        self,
        session_id: uuid.UUID,
        missed_key_points: list[str] | None = None,
        previous_question: str | None = None,
        transcript: str | None = None,
    ) -> Question | None:
        """Create and queue a Groq-generated follow-up when the answer needs probing."""
        session = await self._get_session(session_id)
        if session is None:
            raise ValueError("Session not found")

        points = missed_key_points or ["core concept coverage"]
        schema = {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "key_points": {"type": "array", "items": {"type": "string"}},
                "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
            },
            "required": ["question", "key_points", "difficulty"],
        }
        prompt = (
            "You are conducting a supportive oral exam. Ask one concise follow-up question that "
            "probes a concept the student did not explain well. Do not repeat the original question. "
            f"Original question: {previous_question or 'Explain the topic.'}\n"
            f"Student answer: {transcript or '(no transcript)'}\n"
            f"Concepts needing clarification: {', '.join(str(point) for point in points[:3])}\n"
            "Return the requested JSON object."
        )
        response = await get_provider().generate(prompt, schema=schema)
        followup_text = (
            str(response.get("question", "")).strip() if isinstance(response, dict) else ""
        )
        if not followup_text:
            return None
        key_points = response.get("key_points", points) if isinstance(response, dict) else points
        difficulty_name = (
            response.get("difficulty", "easy") if isinstance(response, dict) else "easy"
        )
        try:
            difficulty = QuestionDifficulty(difficulty_name)
        except ValueError:
            difficulty = QuestionDifficulty.EASY

        followup_question = Question(
            topic_id=next(
                iter(
                    (
                        await self.db.execute(
                            select(Topic.id).where(Topic.course_id == session.course_id).limit(1)
                        )
                    )
                    .scalars()
                    .all()
                ),
                None,
            ),
            question_text=followup_text,
            expected_key_points=list(key_points) if isinstance(key_points, list) else list(points),
            difficulty=difficulty,
            is_approved=True,
            generated_by=session.student_id,
            prompt_version="followup_v1",
        )
        if followup_question.topic_id is None:
            return None

        self.db.add(followup_question)
        await self.db.commit()
        await self.db.refresh(followup_question)
        config = dict(session.config or {})
        order = list(config.get("question_order", []))
        order.insert(session.current_question_index, str(followup_question.id))
        config["question_order"] = order
        session.config = config
        await self.db.commit()
        return followup_question
