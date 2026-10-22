"""Service for turning syllabus chunks into structured oral-exam questions."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import LLMProvider
from app.models.prompt_version import PromptVersion
from app.models.question import Question, QuestionDifficulty
from app.services.llm_service import get_provider

logger = logging.getLogger(__name__)

PROMPT_FILE = Path(__file__).resolve().parent.parent / "llm" / "prompts" / "question_gen_v1.txt"

QUESTION_ARRAY_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "key_points": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "difficulty": {
                        "type": "string",
                        "enum": ["easy", "medium", "hard"],
                    },
                },
                "required": ["question", "key_points", "difficulty"],
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}


class QuestionService:
    """Generate, deduplicate, and persist question-bank entries from topic material."""

    def __init__(self) -> None:
        self.prompt_name = "question_gen"
        self.prompt_version = "v1"

    def _load_prompt_template(self) -> str:
        """Load prompt template string from disk."""
        if PROMPT_FILE.exists():
            return PROMPT_FILE.read_text(encoding="utf-8")
        return (
            "You are an oral examiner creating viva voce questions.\n"
            "Topic Name: {topic_name}\n"
            "Syllabus:\n{context}\n"
            "Generate {count} questions with key_points and difficulty (easy, medium, hard)."
        )

    async def _ensure_prompt_version(self, db: AsyncSession, template: str) -> None:
        """Register the prompt version in the database on first use."""
        stmt = select(PromptVersion).where(
            PromptVersion.name == self.prompt_name,
            PromptVersion.version == self.prompt_version,
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing is None:
            pv = PromptVersion(
                name=self.prompt_name,
                version=self.prompt_version,
                template=template,
                is_active=True,
            )
            db.add(pv)
            await db.commit()

    @staticmethod
    def _normalize_question(item: dict) -> dict[str, Any]:
        """Validate and normalize a model-produced question before persistence."""
        if not isinstance(item, dict):
            raise ValueError("Groq returned an invalid question.")
        difficulty = str(item.get("difficulty", "medium")).lower()
        if difficulty not in {"easy", "medium", "hard"}:
            raise ValueError("Groq returned an unsupported question difficulty.")

        raw_points = item.get("key_points") or item.get("expected_key_points")
        if not isinstance(raw_points, list) or any(
            not isinstance(point, str) for point in raw_points
        ):
            raise ValueError("Groq returned invalid expected answer points.")

        cleaned_points = [str(pt).strip() for pt in raw_points if str(pt).strip()]
        if not cleaned_points:
            raise ValueError("Groq returned a question without expected answer points.")

        question_text = item.get("question") or item.get("question_text")
        if not isinstance(question_text, str) or not question_text.strip():
            raise ValueError("Groq returned an empty question.")

        return {
            "question": question_text.strip(),
            "key_points": cleaned_points,
            "difficulty": difficulty,
        }

    async def generate_questions(
        self,
        topic_id: uuid.UUID,
        context_chunks: list[str],
        count: int = 5,
        topic_name: str = "Topic",
        llm_provider: LLMProvider | None = None,
        db: AsyncSession | None = None,
    ) -> list[dict[str, Any]]:
        """Generate structured exam questions using retrieved context and persist them."""
        if llm_provider is None:
            llm_provider = get_provider()

        template = self._load_prompt_template()
        if db is not None:
            try:
                await self._ensure_prompt_version(db, template)
            except Exception as exc:
                logger.warning("Could not persist prompt version: %s", exc)

        context_text = (
            "\n\n".join(context_chunks[:10]) if context_chunks else "No content available."
        )
        formatted_prompt = (
            template.replace("{topic_name}", str(topic_name))
            .replace("{context}", context_text)
            .replace("{count}", str(count))
        )

        generated_raw: list[dict[str, Any]] = []
        try:
            res = await llm_provider.generate(formatted_prompt, schema=QUESTION_ARRAY_SCHEMA)
            if isinstance(res, list):
                generated_raw = [self._normalize_question(item) for item in res]
            elif (
                isinstance(res, dict) and "questions" in res and isinstance(res["questions"], list)
            ):
                generated_raw = [self._normalize_question(item) for item in res["questions"]]
        except Exception as exc:
            logger.error("Groq question generation failed: %s", exc)
            raise

        if not generated_raw:
            raise RuntimeError(
                "Groq returned no questions. Verify the configured model and try again."
            )

        normalized_candidates = generated_raw[:count]

        # Deduplication against already existing questions in DB
        final_questions: list[dict[str, Any]] = []
        existing_texts: set[str] = set()

        if db is not None:
            stmt = select(Question.question_text).where(Question.topic_id == topic_id)
            rows = (await db.execute(stmt)).scalars().all()
            existing_texts = {text.strip().lower() for text in rows}

            for item in normalized_candidates:
                q_text = item["question"]
                if q_text.strip().lower() in existing_texts:
                    # Duplicate question, skip adding duplicate to DB
                    continue

                new_question = Question(
                    topic_id=topic_id,
                    question_text=q_text,
                    expected_key_points=item["key_points"],
                    difficulty=QuestionDifficulty(item["difficulty"]),
                    prompt_version=f"{self.prompt_name}_{self.prompt_version}",
                    is_approved=False,
                )
                db.add(new_question)
                existing_texts.add(q_text.strip().lower())
                final_questions.append(item)

            await db.commit()
        else:
            final_questions = normalized_candidates

        return final_questions if final_questions else normalized_candidates
