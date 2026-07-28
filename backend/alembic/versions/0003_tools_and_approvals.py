"""add tool calls approvals and artifacts

Revision ID: 0003_tools_and_approvals
Revises: 0002_planning
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_tools_and_approvals"
down_revision = "0002_planning"
branch_labels = None
depends_on = None

approval_status = sa.Enum(
    "PENDING", "APPROVED_ONCE", "APPROVED_FOR_TASK", "DENIED", "EXPIRED",
    name="approvalstatus",
)
tool_call_status = sa.Enum(
    "REQUESTED", "WAITING_APPROVAL", "RUNNING", "SUCCEEDED", "FAILED", "REJECTED",
    name="toolcallstatus",
)


def upgrade():
    op.create_table(
        "tool_calls",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.String(36), sa.ForeignKey("task_nodes.id", ondelete="SET NULL")),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("status", tool_call_status, nullable=False),
        sa.Column("result_summary", sa.Text()),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_tool_calls_task_id", "tool_calls", ["task_id"])
    op.create_table(
        "approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_call_id", sa.String(36), sa.ForeignKey("tool_calls.id", ondelete="CASCADE")),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("risk", sa.String(32), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("status", approval_status, nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decided_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
    )
    op.create_index("ix_approvals_task_id", "approvals", ["task_id"])
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.String(36), sa.ForeignKey("task_nodes.id", ondelete="SET NULL")),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("relative_path", sa.String(1000), nullable=False),
        sa.Column("mime_type", sa.String(255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("is_final", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_artifacts_task_id", "artifacts", ["task_id"])


def downgrade():
    op.drop_table("artifacts")
    op.drop_table("approvals")
    op.drop_table("tool_calls")
    tool_call_status.drop(op.get_bind(), checkfirst=True)
    approval_status.drop(op.get_bind(), checkfirst=True)
