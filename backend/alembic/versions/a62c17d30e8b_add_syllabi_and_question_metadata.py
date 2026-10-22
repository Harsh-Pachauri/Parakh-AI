"""Add persisted course syllabi and question-bank metadata.

Revision ID: a62c17d30e8b
Revises: 8b2c1a7e9d41
Create Date: 2026-10-22 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a62c17d30e8b"
down_revision: str | Sequence[str] | None = "8b2c1a7e9d41"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("subject", sa.String(length=255), nullable=True))
    op.add_column("courses", sa.Column("academic_level", sa.String(length=100), nullable=True))
    op.add_column("courses", sa.Column("syllabus_text", sa.Text(), nullable=True))
    op.add_column("courses", sa.Column("syllabus_analysis", sa.JSON(), nullable=True))
    op.add_column(
        "courses",
        sa.Column("interview_config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "questions",
        sa.Column(
            "tags",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column("questions", sa.Column("question_type", sa.String(length=50), nullable=True))
    op.add_column("questions", sa.Column("explanation", sa.Text(), nullable=True))
    op.create_index(
        "uq_answers_session_question", "answers", ["session_id", "question_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_answers_session_question", table_name="answers")
    op.drop_column("questions", "explanation")
    op.drop_column("questions", "question_type")
    op.drop_column("questions", "tags")
    op.drop_column("courses", "syllabus_analysis")
    op.drop_column("courses", "syllabus_text")
    op.drop_column("courses", "interview_config")
    op.drop_column("courses", "academic_level")
    op.drop_column("courses", "subject")
