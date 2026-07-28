"""add per-task model strategy

Revision ID: 0008_task_model_mode
Revises: 0007_review_retry
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_task_model_mode"
down_revision = "0007_review_retry"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tasks",
        sa.Column("model_mode", sa.String(length=32), nullable=False, server_default="auto"),
    )


def downgrade():
    op.drop_column("tasks", "model_mode")
