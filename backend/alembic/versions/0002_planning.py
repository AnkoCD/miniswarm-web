"""add task nodes and api usage

Revision ID: 0002_planning
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_planning"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

node_status = sa.Enum(
    "PENDING", "READY", "QUEUED", "RUNNING", "WAITING", "SUCCEEDED",
    "FAILED", "RETRYING", "CANCELED", "SKIPPED", name="nodestatus"
)


def upgrade():
    op.create_table(
        "task_nodes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_key", sa.String(64), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("depends_on", sa.JSON(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("status", node_status, nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("result_summary", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_task_nodes_task_id", "task_nodes", ["task_id"])
    op.create_index("ix_task_nodes_task_status", "task_nodes", ["task_id", "status"])
    op.create_table(
        "api_usage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_hit_tokens", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_api_usage_task_id", "api_usage", ["task_id"])


def downgrade():
    op.drop_table("api_usage")
    op.drop_table("task_nodes")
    node_status.drop(op.get_bind(), checkfirst=True)
