"""Add institutions table and user institution_id column.

Revision ID: c74d82f19a0e
Revises: a62c17d30e8b
Create Date: 2026-10-23 17:50:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c74d82f19a0e"
down_revision: str | Sequence[str] | None = "a62c17d30e8b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "institutions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_institutions_code", "institutions", ["code"], unique=True)
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("institution_id", sa.Uuid(as_uuid=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_users_institution_id",
            "institutions",
            ["institution_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_users_institution_id", ["institution_id"])


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_institution_id")
        batch_op.drop_constraint("fk_users_institution_id", type_="foreignkey")
        batch_op.drop_column("institution_id")
    op.drop_index("ix_institutions_code", table_name="institutions")
    op.drop_table("institutions")
