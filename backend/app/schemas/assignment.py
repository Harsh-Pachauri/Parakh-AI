"""Pydantic schemas for assignment management and scheduling."""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class AssignmentCreate(BaseModel):
    """Schema for creating a scheduled assessment assignment."""

    course_id: uuid.UUID
    assessment_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=255)
    instructions: str | None = None
    start_date: datetime | None = None
    deadline: datetime | None = None
    attempt_limit: int = Field(default=1, ge=1, le=100)
    is_active: bool = True
    assigned_student_ids: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Assignment title cannot be blank")
        return s

    @model_validator(mode="after")
    def validate_dates(self) -> "AssignmentCreate":
        start = self.start_date
        end = self.deadline
        if start and start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
            self.start_date = start
        if end and end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
            self.deadline = end
        if start and end and start >= end:
            raise ValueError("Start date must be before deadline")
        return self


class AssignmentUpdate(BaseModel):
    """Schema for updating an existing assignment."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    instructions: str | None = None
    start_date: datetime | None = None
    deadline: datetime | None = None
    attempt_limit: int | None = Field(default=None, ge=1, le=100)
    is_active: bool | None = None
    assigned_student_ids: list[str] | None = None
    config: dict[str, Any] | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: str | None) -> str | None:
        if v is not None:
            s = v.strip()
            if not s:
                raise ValueError("Assignment title cannot be blank")
            return s
        return v

    @model_validator(mode="after")
    def validate_dates(self) -> "AssignmentUpdate":
        start = self.start_date
        end = self.deadline
        if start and start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
            self.start_date = start
        if end and end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
            self.deadline = end
        if start and end and start >= end:
            raise ValueError("Start date must be before deadline")
        return self


class AssignmentResponse(BaseModel):
    """Schema for returning assignment details to teachers."""

    id: uuid.UUID
    teacher_id: uuid.UUID
    course_id: uuid.UUID
    assessment_id: uuid.UUID
    title: str
    instructions: str | None = None
    start_date: datetime | None = None
    deadline: datetime | None = None
    attempt_limit: int
    is_active: bool
    assigned_student_ids: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    # Computed fields
    course_name: str | None = None
    course_code: str | None = None
    assessment_title: str | None = None
    duration_minutes: int | None = None
    status: str = "active"  # "scheduled", "active", "closed"
    total_submissions: int = 0
    completed_count: int = 0
    average_score: float | None = None

    model_config = {"from_attributes": True}


class StudentAssignmentResponse(BaseModel):
    """Schema for displaying assigned assessments to students."""

    id: uuid.UUID
    course_id: uuid.UUID
    assessment_id: uuid.UUID
    title: str
    instructions: str | None = None
    course_name: str | None = None
    course_code: str | None = None
    duration_minutes: int | None = None
    start_date: datetime | None = None
    deadline: datetime | None = None
    attempt_limit: int = 1
    attempts_used: int = 0
    status: str = "available"  # "available", "scheduled", "submitted", "overdue", "closed"
    latest_session_id: uuid.UUID | None = None
    latest_score: float | None = None
    can_launch: bool = False

    model_config = {"from_attributes": True}


class AssignmentSubmissionItem(BaseModel):
    """Individual submission / attempt record under an assignment."""

    session_id: uuid.UUID
    student_id: uuid.UUID
    student_name: str
    student_email: str
    status: str
    score: float | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class AssignmentSubmissionsResponse(BaseModel):
    """Teacher view of all student submissions and statistics for an assignment."""

    assignment_id: uuid.UUID
    title: str
    course_name: str | None = None
    total_eligible_students: int = 0
    total_submissions: int = 0
    completed_count: int = 0
    average_score: float | None = None
    submissions: list[AssignmentSubmissionItem] = Field(default_factory=list)

    model_config = {"from_attributes": True}
