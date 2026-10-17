"""Keep profile/target history without inventing values for past dates."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "f16c6106a002"
down_revision = "e43c6103b001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "profile_revisions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("profile_snapshot", JSONB(), nullable=False),
        sa.Column("targets", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_profile_revisions_user_date",
        "profile_revisions",
        ["user_id", "effective_date", "created_at"],
    )


def downgrade():
    op.drop_table("profile_revisions")
