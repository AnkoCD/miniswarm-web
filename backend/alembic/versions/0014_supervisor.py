"""add task supervisor and versioned briefs

Revision ID: 0014_supervisor
Revises: 0013_codex_workspace
"""
from alembic import op
import sqlalchemy as sa


revision = "0014_supervisor"
down_revision = "0013_codex_workspace"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tasks", sa.Column("brief_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("tasks", sa.Column("supervisor_status", sa.String(24), nullable=False, server_default="IDLE"))
    op.add_column("task_nodes", sa.Column("target_brief_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("task_nodes", sa.Column("applied_brief_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("artifacts", sa.Column("brief_version", sa.Integer(), nullable=False, server_default="1"))

    op.create_table(
        "task_directives",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("task_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("kind", sa.String(24), nullable=False, server_default="unknown"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("affected_node_keys", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("requires_replan", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("applied_brief_version", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_task_directives_task_id", "task_directives", ["task_id"])
    op.create_index("ix_task_directives_message_id", "task_directives", ["message_id"])
    op.create_index("ix_task_directives_task_status", "task_directives", ["task_id", "status"])
    op.create_index("ux_task_directives_message", "task_directives", ["message_id"], unique=True)

    op.create_table(
        "task_brief_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("change_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_directive_id", sa.String(36), sa.ForeignKey("task_directives.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_task_brief_versions_task_id", "task_brief_versions", ["task_id"])
    op.create_index("ux_task_brief_task_version", "task_brief_versions", ["task_id", "version"], unique=True)


def downgrade():
    op.drop_table("task_brief_versions")
    op.drop_table("task_directives")
    op.drop_column("artifacts", "brief_version")
    op.drop_column("task_nodes", "applied_brief_version")
    op.drop_column("task_nodes", "target_brief_version")
    op.drop_column("tasks", "supervisor_status")
    op.drop_column("tasks", "brief_version")
