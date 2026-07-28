"""track one-time approval consumption

Revision ID: 0004_approval_consumption
Revises: 0003_tools_and_approvals
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_approval_consumption"
down_revision = "0003_tools_and_approvals"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("approvals", sa.Column("consumed_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_column("approvals", "consumed_at")

