"""Preserve nutrient definitions and source verification in food imports."""
from alembic import op
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB

revision = "d42c6102a001"
down_revision = "c93f5a17d284"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("foods", Column("nutrition_meta", JSONB(), nullable=True))


def downgrade():
    op.drop_column("foods", "nutrition_meta")
