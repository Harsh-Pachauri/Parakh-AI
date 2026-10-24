"""Pydantic schemas for custom viva assessments."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.question import QuestionResponse


class AssessmentCreate(BaseModel):
    """Payload for creating a custom oral exam assessment."""

    course_id: uuid.UUID
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    instructions: str | None = None
    duration_minutes: int = Field(default=15, ge=1, le=180)
    max_questions: int = Field(default=5, ge=1, le=20)
    difficulty: str = Field(default="medium")
    is_published: bool = False
    topic_ids: list[uuid.UUID] = Field(default_factory=list)
    question_ids: list[uuid.UUID] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


class AssessmentUpdate(BaseModel):
    """Payload for updating an existing assessment."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    instructions: str | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=180)
    max_questions: int | None = Field(default=None, ge=1, le=20)
    difficulty: str | None = None
    is_published: bool | None = None
    topic_ids: list[uuid.UUID] | None = None
    question_ids: list[uuid.UUID] | None = None
    config: dict[str, Any] | None = None


class AssessmentResponse(BaseModel):
    """Complete assessment representation returned to teachers."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    teacher_id: uuid.UUID
    course_id: uuid.UUID
    course_name: str | None = None
    course_code: str | None = None
    title: str
    description: str | None = None
    instructions: str | None = None
    duration_minutes: int = 15
    max_questions: int = 5
    difficulty: str = "medium"
    is_published: bool = False
    topic_ids: list[uuid.UUID] = Field(default_factory=list)
    question_ids: list[uuid.UUID] = Field(default_factory=list)
    question_count: int = 0
    questions: list[QuestionResponse] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class StudentAssessmentResponse(BaseModel):
    """Published assessment payload displayed to students."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: uuid.UUID
    course_name: str
    course_code: str
    title: str
    description: str | None = None
    instructions: str | None = None
    duration_minutes: int
    max_questions: int
    difficulty: str
    question_count: int
    start_url: str
    user_attempts_count: int = 0
    latest_score_percent: str | None = None
