"""Persist cancelled turns and link each assistant reply to its user message."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "e43c6103b001"
down_revision = "d42c6102a001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "messages", sa.Column("cancelled", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("messages", sa.Column("reply_to_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_messages_reply_to_id",
        "messages",
        "messages",
        ["reply_to_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_messages_reply_to_id", "messages", ["reply_to_id"])


def downgrade():
    op.drop_index("ix_messages_reply_to_id", table_name="messages")
    op.drop_constraint("fk_messages_reply_to_id", "messages", type_="foreignkey")
    op.drop_column("messages", "reply_to_id")
    op.drop_column("messages", "cancelled")
