"""add task autonomy mode

Revision ID: 0010_task_autonomy_mode
Revises: 0009_task_conversation
"""
from alembic import op
import sqlalchemy as sa


revision = "0010_task_autonomy_mode"
down_revision = "0009_task_conversation"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tasks",
        sa.Column("autonomy_mode", sa.String(32), nullable=False, server_default="safe"),
    )


def downgrade():
    op.drop_column("tasks", "autonomy_mode")
