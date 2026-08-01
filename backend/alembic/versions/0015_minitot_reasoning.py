"""add MiniTot reasoning profiles

Revision ID: 0015_minitot_reasoning
Revises: 0014_supervisor
"""
from alembic import op
import sqlalchemy as sa


revision = "0015_minitot_reasoning"
down_revision = "0014_supervisor"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tasks",
        sa.Column("reasoning_mode", sa.String(32), nullable=False, server_default="auto"),
    )
    op.add_column(
        "tasks",
        sa.Column("reasoning_effort", sa.String(32), nullable=False, server_default="smart"),
    )
    op.execute(
        "UPDATE tasks SET reasoning_mode = CASE WHEN execution_mode = 'deep' "
        "THEN 'auto' ELSE 'direct' END, reasoning_effort = CASE WHEN execution_mode = 'deep' "
        "THEN 'high' ELSE 'fast' END"
    )
    op.add_column(
        "task_messages",
        sa.Column("reasoning_mode", sa.String(32), nullable=True),
    )
    op.add_column(
        "task_messages",
        sa.Column("reasoning_effort", sa.String(32), nullable=True),
    )


def downgrade():
    op.drop_column("task_messages", "reasoning_effort")
    op.drop_column("task_messages", "reasoning_mode")
    op.drop_column("tasks", "reasoning_effort")
    op.drop_column("tasks", "reasoning_mode")
