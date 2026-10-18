"""Email OTP before setting the first password.

Revision ID: f16c6106a003
Revises: f16c6106a001
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "f16c6106a003"
down_revision = "f16c6106a001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "registration_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("setup_token_hash", sa.String(64)),
        sa.Column("setup_expires_at", sa.DateTime(timezone=True)),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("consent_version", sa.String(32), nullable=False),
        sa.CheckConstraint("attempts >= 0 AND attempts <= 5", name="ck_registration_attempts"),
    )
    op.create_index("ix_registration_challenges_email", "registration_challenges", ["email"])
    op.create_index(
        "ix_registration_challenges_expires_at", "registration_challenges", ["expires_at"]
    )


def downgrade():
    op.drop_table("registration_challenges")
