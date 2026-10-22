"""Question generation and review schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.question import QuestionDifficulty


class QuestionGenerateRequest(BaseModel):
    """Request body for creating exam questions from topic content."""

    count: int = Field(default=5, ge=1, le=10)


class QuestionResponse(BaseModel):
    """Question payload returned to clients."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    topic_id: uuid.UUID
    question_text: str
    expected_key_points: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    question_type: str | None = None
    explanation: str | None = None
    difficulty: QuestionDifficulty
    is_approved: bool = False
    generated_by: uuid.UUID | None = None
    prompt_version: str | None = None
    avg_score: float | None = None
    times_used: int = 0
    created_at: datetime


class QuestionUpdate(BaseModel):
    """Schema for editing an existing generated question."""

    question_text: str | None = Field(default=None, min_length=1)
    expected_key_points: list[str] | None = None
    difficulty: QuestionDifficulty | None = None
    is_approved: bool | None = None
    tags: list[str] | None = None
    question_type: str | None = Field(default=None, max_length=50)
    explanation: str | None = None


class QuestionCreate(BaseModel):
    """Teacher-authored question-bank entry."""

    topic_id: uuid.UUID
    question_text: str = Field(min_length=1, max_length=12000)
    expected_key_points: list[str] = Field(min_length=1, max_length=50)
    difficulty: QuestionDifficulty = QuestionDifficulty.MEDIUM
    tags: list[str] = Field(default_factory=list, max_length=30)
    question_type: str | None = Field(default=None, max_length=50)
    explanation: str | None = None


class QuestionPageResponse(BaseModel):
    """Paginated question-bank results."""

    items: list[QuestionResponse]
    total: int
    offset: int
    limit: int
