"""Assessment database model for teacher-authored custom vivas."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.assignment import Assignment
    from app.models.course import Course
    from app.models.user import User


class Assessment(Base):
    """Custom oral examination / assessment created by a teacher."""

    __tablename__ = "assessments"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    instructions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    duration_minutes: Mapped[int] = mapped_column(
        Integer,
        default=15,
        nullable=False,
    )
    max_questions: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False,
    )
    difficulty: Mapped[str] = mapped_column(
        String(20),
        default="medium",
        nullable=False,
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )
    topic_ids: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        server_default=text("'[]'"),
        nullable=False,
    )
    question_ids: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        server_default=text("'[]'"),
        nullable=False,
    )
    config: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    teacher: Mapped["User"] = relationship(
        "User",
        back_populates="assessments",
    )
    course: Mapped["Course"] = relationship(
        "Course",
        back_populates="assessments",
    )
    assignments: Mapped[list["Assignment"]] = relationship(
        "Assignment",
        back_populates="assessment",
        cascade="all, delete-orphan",
    )
