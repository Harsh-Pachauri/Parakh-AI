"""Answer database model."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.question import Question
    from app.models.score_override import ScoreOverride
    from app.models.viva_session import VivaSession


class Answer(Base):
    """An answer submitted by a student to a specific viva question."""

    __tablename__ = "answers"
    __table_args__ = (
        Index("uq_answers_session_question", "session_id", "question_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("viva_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence_number: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )
    transcript: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    embedding_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    llm_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    fused_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    rubric_breakdown: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    llm_raw_response: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    audio_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    is_followup: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    transcription_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    latency_ms: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    session: Mapped["VivaSession"] = relationship(
        "VivaSession",
        back_populates="answers",
    )
    question: Mapped["Question"] = relationship(
        "Question",
        back_populates="answers",
    )
    score_override: Mapped[Optional["ScoreOverride"]] = relationship(
        "ScoreOverride",
        back_populates="answer",
        uselist=False,
        cascade="all, delete-orphan",
    )
