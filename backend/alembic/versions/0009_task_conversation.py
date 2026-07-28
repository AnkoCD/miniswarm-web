"""add task conversation and revision tracking

Revision ID: 0009_task_conversation
Revises: 0008_task_model_mode
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_task_conversation"
down_revision = "0008_task_model_mode"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tasks",
        sa.Column("current_revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "task_nodes",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "task_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False, server_default="chat"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_task_messages_task_id", "task_messages", ["task_id"])
    op.create_index("ix_task_messages_task_created", "task_messages", ["task_id", "created_at"])


def downgrade():
    op.drop_table("task_messages")
    op.drop_column("task_nodes", "revision")
    op.drop_column("tasks", "current_revision")
