"""add users.consented_at / users.consent_version

Revision ID: c93f5a17d284
Revises: b7d2e41c9f10
Create Date: 2026-09-08

The service stores health-adjacent personal data (sex, birth date, height,
weight, body-fat percentage), so the consent that permits it has to survive as
evidence rather than as a checkbox that disappears with the page.

Both columns are nullable: accounts that existed before this migration carry no
consent record, and back-filling one would fabricate agreement nobody gave.
A NULL here means "we do not have a record", which is the truth.
"""

from alembic import op
import sqlalchemy as sa

revision = "c93f5a17d284"
down_revision = "b7d2e41c9f10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("users", sa.Column("consent_version", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "consent_version")
    op.drop_column("users", "consented_at")
