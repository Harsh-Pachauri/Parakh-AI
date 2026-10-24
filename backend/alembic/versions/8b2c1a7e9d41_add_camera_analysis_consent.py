"""Add explicit consent for local camera cue analysis."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8b2c1a7e9d41"
down_revision: str | Sequence[str] | None = "f32ab3356408"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "consents",
        sa.Column("camera_analysis_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("consents", "camera_analysis_consent")
