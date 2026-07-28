"""add global memory and archive analysis

Revision ID: 0011_global_memory
Revises: 0010_task_autonomy_mode
"""
from alembic import op
import sqlalchemy as sa


revision = "0011_global_memory"
down_revision = "0010_task_autonomy_mode"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_memories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("memory_key", sa.String(120), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("source_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="SET NULL")),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_memories_user_id", "user_memories", ["user_id"])
    op.create_index("ix_user_memories_source_task_id", "user_memories", ["source_task_id"])
    op.create_index("ix_user_memories_user_status", "user_memories", ["user_id", "status"])
    op.create_index(
        "ux_user_memories_user_key",
        "user_memories",
        ["user_id", "category", "memory_key"],
        unique=True,
    )

    op.create_table(
        "memory_extractions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("task_summary", sa.Text()),
        sa.Column("habit_summary_delta", sa.Text()),
        sa.Column("memory_items_count", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("task_id", name="uq_memory_extractions_task_id"),
    )
    op.create_index("ix_memory_extractions_user_id", "memory_extractions", ["user_id"])
    op.create_index("ix_memory_extractions_task_id", "memory_extractions", ["task_id"])
    op.create_index(
        "ix_memory_extractions_user_status", "memory_extractions", ["user_id", "status"]
    )

    op.create_table(
        "user_memory_profiles",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("defaults_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "memory_revisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("memory_id", sa.String(36), sa.ForeignKey("user_memories.id", ondelete="SET NULL")),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=False),
        sa.Column("after_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_memory_revisions_user_id", "memory_revisions", ["user_id"])
    op.create_index(
        "ix_memory_revisions_user_created", "memory_revisions", ["user_id", "created_at"]
    )


def downgrade():
    op.drop_table("memory_revisions")
    op.drop_table("user_memory_profiles")
    op.drop_table("memory_extractions")
    op.drop_table("user_memories")
