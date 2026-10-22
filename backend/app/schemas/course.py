"""Course and Topic request and response schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CourseInterviewConfig(BaseModel):
    """Teacher-configured defaults for student interviews."""

    max_questions: int = Field(default=5, ge=1, le=10)
    max_duration_sec: int = Field(default=900, ge=60, le=7200)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    topic_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)


class TopicBase(BaseModel):
    """Base fields for topic."""

    name: str = Field(..., min_length=1, max_length=255)
    sort_order: int = Field(default=0, ge=0)


class TopicCreate(TopicBase):
    """Schema for creating a topic in a course."""

    pass


class TopicUpdate(BaseModel):
    """Schema for updating topic attributes."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    sort_order: int | None = Field(default=None, ge=0)


class TopicResponse(TopicBase):
    """Schema for returning topic details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: uuid.UUID
    created_at: datetime


class CourseBase(BaseModel):
    """Base fields for course."""

    name: str = Field(..., min_length=1, max_length=255)
    code: str = Field(..., min_length=1, max_length=50)
    subject: str | None = Field(default=None, max_length=255)
    description: str | None = None
    academic_level: str | None = Field(default=None, max_length=100)
    syllabus_text: str | None = None
    interview_config: CourseInterviewConfig = Field(default_factory=CourseInterviewConfig)


class CourseCreate(CourseBase):
    """Schema for creating a course."""

    pass


class CourseUpdate(BaseModel):
    """Schema for updating a course."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=50)
    subject: str | None = Field(default=None, max_length=255)
    description: str | None = None
    academic_level: str | None = Field(default=None, max_length=100)
    syllabus_text: str | None = None
    interview_config: CourseInterviewConfig | None = None


class CourseResponse(CourseBase):
    """Schema for returning course details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    teacher_id: uuid.UUID
    created_at: datetime
    topics: list[TopicResponse] = Field(default_factory=list)
    syllabus_analysis: dict | None = None
    interview_config: CourseInterviewConfig = Field(default_factory=CourseInterviewConfig)
