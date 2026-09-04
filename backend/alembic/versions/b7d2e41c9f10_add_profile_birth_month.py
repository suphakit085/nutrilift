"""add profiles.birth_month

Revision ID: b7d2e41c9f10
Revises: 8374a3d906e7
Create Date: 2026-09-04

With a birth year alone, anyone born in December 2008 counted as 18 from
1 January 2026. The month lets the age gate round down instead.
"""

from alembic import op
import sqlalchemy as sa

revision = "b7d2e41c9f10"
down_revision = "8374a3d906e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("birth_month", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_profiles_birth_month",
        "profiles",
        "birth_month IS NULL OR birth_month BETWEEN 1 AND 12",
    )


def downgrade() -> None:
    op.drop_constraint("ck_profiles_birth_month", "profiles", type_="check")
    op.drop_column("profiles", "birth_month")
