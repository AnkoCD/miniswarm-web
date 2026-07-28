"""track reviewer rework count

Revision ID: 0007_review_retry
Revises: 0006_task_soft_delete
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_review_retry"
down_revision = "0006_task_soft_delete"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tasks", sa.Column("review_retries", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("tasks", "review_retries")
