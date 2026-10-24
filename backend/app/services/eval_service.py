"""Hybrid scoring engine for viva answers."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.llm.groq import GroqRequestError
from app.services.rag_service import cosine_similarity, embed_chunks

logger = logging.getLogger(__name__)


class RubricScore(BaseModel):
    """Structured rubric score for a viva answer."""

    correctness: float = Field(..., ge=0, le=10)
    completeness: float = Field(..., ge=0, le=10)
    clarity: float = Field(..., ge=0, le=10)
    justification: str = ""
    llm_score: float = Field(default=0.0, ge=0, le=1.0)

    @property
    def average(self) -> float:
        """Return the rubric mean in the 0-10 scale."""
        return (self.correctness + self.completeness + self.clarity) / 3.0

    @property
    def normalized_score(self) -> float:
        """Return the normalized score in the 0-1 range."""
        return max(0.0, min(1.0, self.average / 10.0))


class EmbeddingSimilarityScorer:
    """Compute semantic relevance between a transcript and key points."""

    @staticmethod
    def _lexical_overlap_score(transcript: str, key_points: list[str]) -> float:
        """Boost similarity when transcript content contains the expected technical keywords."""

        def normalize_tokens(value: str) -> set[str]:
            return {
                token.lower()
                for token in re.findall(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*", str(value).lower())
            }

        text_tokens = normalize_tokens(transcript)
        if not text_tokens:
            return 0.0

        overlaps: list[float] = []
        for point in key_points:
            point_tokens = normalize_tokens(point)
            if not point_tokens:
                continue
            overlaps.append(len(text_tokens & point_tokens) / max(len(point_tokens), 1))

        return float(sum(overlaps) / len(overlaps)) if overlaps else 0.0

    def score(self, transcript: str, key_points: list[str]) -> float:
        """Return a 0-1 similarity score using embedding cosine similarity."""
        text = (transcript or "").strip()
        points = [str(point).strip() for point in (key_points or []) if str(point).strip()]

        if not text or not points:
            return 0.0

        transcript_vector = embed_chunks([text])[0]
        similarities: list[float] = []
        for point in points:
            point_vector = embed_chunks([point])[0]
            score = max(0.0, cosine_similarity(transcript_vector, point_vector))
            similarities.append(score)

        if not similarities:
            return 0.0

        embedding_score = float(sum(similarities) / len(similarities))
        lexical_score = self._lexical_overlap_score(text, points)
        return float(max(embedding_score, lexical_score))


class LLMJudgeScorer:
    """Ask an LLM to score a transcript against rubric criteria."""

    def __init__(self, provider: Any | None = None, max_retries: int = 2) -> None:
        self.provider = provider
        self.max_retries = max_retries

    @staticmethod
    def _prompt_template() -> str:
        template_path = Path(__file__).resolve().parent.parent / "llm" / "prompts" / "judge_v1.txt"
        if template_path.exists():
            return template_path.read_text(encoding="utf-8")
        return (
            "You are grading a viva answer.\n"
            "Question: {question}\n"
            "Student answer: {transcript}\n"
            "Expected key points: {key_points}\n"
            "Return valid JSON with keys: correctness, completeness, clarity, justification.\n"
            "All scores must be numbers between 0 and 10."
        )

    @staticmethod
    def _schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "correctness": {"type": "number", "minimum": 0, "maximum": 10},
                "completeness": {"type": "number", "minimum": 0, "maximum": 10},
                "clarity": {"type": "number", "minimum": 0, "maximum": 10},
                "justification": {"type": "string"},
            },
            "required": ["correctness", "completeness", "clarity", "justification"],
            "additionalProperties": False,
        }

    async def score(
        self,
        question: str,
        transcript: str,
        key_points: list[str],
    ) -> RubricScore:
        """Judge a transcript against the rubric and return a structured score."""
        text = (transcript or "").strip()
        if not text:
            return RubricScore(
                correctness=0.0,
                completeness=0.0,
                clarity=0.0,
                justification="No transcript available for scoring.",
                llm_score=0.0,
            )

        provider = self.provider
        if provider is None:
            from app.services.llm_service import get_provider

            provider = get_provider()

        prompt = self._prompt_template()
        prompt = prompt.replace("{question}", str(question))
        prompt = prompt.replace("{transcript}", text)
        prompt = prompt.replace(
            "{key_points}", "\n- ".join(str(point) for point in key_points or [])
        )

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                request_prompt = prompt
                if attempt:
                    request_prompt += (
                        "\nYour previous response did not validate. Return a corrected JSON "
                        "object with all required numeric rubric fields and no additional text."
                    )
                response = await provider.generate(request_prompt, schema=self._schema())
                if not isinstance(response, dict):
                    raise ValueError("Groq judge returned a non-object response.")
                required = {"correctness", "completeness", "clarity"}
                if not required.issubset(response):
                    raise ValueError("Groq judge omitted required rubric fields.")

                normalization = {
                    "correctness": float(response["correctness"]),
                    "completeness": float(response["completeness"]),
                    "clarity": float(response["clarity"]),
                    "justification": str(
                        response.get("justification") or "No justification provided."
                    )[:1000],
                }
                rubric = RubricScore(**normalization)
                rubric.llm_score = float(
                    (rubric.correctness + rubric.completeness + rubric.clarity) / 30.0
                )
                return rubric
            except GroqRequestError as exc:
                raise RuntimeError(str(exc)) from exc
            except (ValueError, TypeError) as exc:
                last_error = exc
                logger.warning("Groq judge response failed schema validation: %s", exc)

        # The judge kept returning unusable output (often for non-answers such as "can we move
        # on?"). Record a conservative score instead of blocking the whole interview.
        logger.error("Groq judge output invalid after retries: %s", last_error)
        return RubricScore(
            correctness=0.0,
            completeness=0.0,
            clarity=0.0,
            justification="Automatic scoring could not evaluate this response; flagged for teacher review.",
            llm_score=0.0,
        )


class ScoreFusion:
    """Combine embedding and LLM scores into a single final score."""

    @staticmethod
    def fuse(
        embedding_score: float,
        llm_score: float,
        weights: tuple[float, float] = (0.4, 0.6),
    ) -> float:
        """Combine semantic similarity and rubric score into a single 0-1 value."""
        if len(weights) != 2:
            raise ValueError("weights must contain exactly two numeric values.")

        w1, w2 = weights
        if sum(weights) == 0:
            return 0.0

        score = (w1 * float(embedding_score) + w2 * float(llm_score)) / sum(weights)
        return max(0.0, min(1.0, float(score)))


async def evaluate_answer(
    question: str,
    transcript: str,
    key_points: list[str],
    provider: Any | None = None,
    weights: tuple[float, float] = (0.4, 0.6),
) -> dict[str, Any]:
    """Run the full evaluation pipeline for one answer."""
    embedding_scorer = EmbeddingSimilarityScorer()
    embedding_score = embedding_scorer.score(transcript, key_points)

    judge = LLMJudgeScorer(provider=provider)
    rubric = await judge.score(question, transcript, key_points)
    fused_score = ScoreFusion.fuse(embedding_score, rubric.llm_score, weights=weights)

    return {
        "embedding_score": embedding_score,
        "llm_score": rubric.llm_score,
        "fused_score": fused_score,
        "rubric": rubric.model_dump(),
    }


__all__ = [
    "EmbeddingSimilarityScorer",
    "LLMJudgeScorer",
    "RubricScore",
    "ScoreFusion",
    "evaluate_answer",
]
