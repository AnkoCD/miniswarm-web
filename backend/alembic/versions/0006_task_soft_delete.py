"""add task soft deletion

Revision ID: 0006_task_soft_delete
Revises: 0005_agent_runs
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_task_soft_delete"
down_revision = "0005_agent_runs"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tasks", sa.Column("deleted_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_column("tasks", "deleted_at")
