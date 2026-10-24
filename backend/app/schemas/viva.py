"""Schemas for viva orchestration state and responses."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class VivaConfig(BaseModel):
    """Session-level configuration for a viva exam."""

    max_questions: int = Field(default=5, ge=1, le=10)
    max_duration_sec: int = Field(default=900, ge=60)
    follow_up_threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    difficulty: Literal["easy", "medium", "hard"] | None = None
    topic_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    question_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)


class VivaStartRequest(BaseModel):
    """Student-selected course and bounded interview settings."""

    course_id: uuid.UUID | None = None
    assessment_id: uuid.UUID | None = None
    assignment_id: uuid.UUID | None = None
    max_questions: int | None = Field(default=None, ge=1, le=10)
    max_duration_sec: int | None = Field(default=None, ge=60, le=7200)
    difficulty: Literal["easy", "medium", "hard"] | None = None
    topic_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)
    is_adaptive: bool | None = None
    practice_mode: Literal["adaptive", "targeted", "standard"] | None = None


class BehaviorFlagCreate(BaseModel):
    """A privacy-preserving cue detected locally by the student's browser."""

    cue_type: str = Field(pattern="^(additional_faces|off_screen_gaze)$")


class InterviewTurnRequest(BaseModel):
    """A finalized candidate utterance from the live interview."""

    question_id: uuid.UUID
    transcript: str = Field(min_length=1, max_length=12000)


class VivaQuestionResponse(BaseModel):
    """Question payload returned when advancing a viva session."""

    model_config = ConfigDict(from_attributes=True)

    session_id: uuid.UUID
    question_id: uuid.UUID
    question_text: str
    opening_greeting: str | None = None
    expected_key_points: list[str] = Field(default_factory=list)
    difficulty: str = "medium"
    current_question_index: int = 0


class VivaSessionSummary(BaseModel):
    """Final summary returned after a viva is completed."""

    model_config = ConfigDict(from_attributes=True)

    session_id: uuid.UUID
    status: str
    total_score: float | None = None
    answers_count: int = 0
    finished_at: datetime | None = None
