"""Add assessments table for custom viva builder.

Revision ID: e41a9d8f3b20
Revises: c74d82f19a0e
Create Date: 2026-10-24 08:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e41a9d8f3b20"
down_revision: str | Sequence[str] | None = "c74d82f19a0e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assessments",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "teacher_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "course_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("max_questions", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("difficulty", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("topic_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("question_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_assessments_teacher_id", "assessments", ["teacher_id"])
    op.create_index("ix_assessments_course_id", "assessments", ["course_id"])
    op.create_index("ix_assessments_is_published", "assessments", ["is_published"])


def downgrade() -> None:
    op.drop_index("ix_assessments_is_published", table_name="assessments")
    op.drop_index("ix_assessments_course_id", table_name="assessments")
    op.drop_index("ix_assessments_teacher_id", table_name="assessments")
    op.drop_table("assessments")
