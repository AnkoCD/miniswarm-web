"""add task skill selection

Revision ID: 0012_task_skills
Revises: 0011_global_memory
"""
from alembic import op
import sqlalchemy as sa


revision = "0012_task_skills"
down_revision = "0011_global_memory"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tasks",
        sa.Column("skill_mode", sa.String(16), nullable=False, server_default="auto"),
    )
    op.add_column(
        "tasks",
        sa.Column("selected_skills", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade():
    op.drop_column("tasks", "selected_skills")
    op.drop_column("tasks", "skill_mode")
