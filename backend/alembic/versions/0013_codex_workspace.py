"""add Codex-style project workspace

Revision ID: 0013_codex_workspace
Revises: 0012_task_skills
"""
from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa


revision = "0013_codex_workspace"
down_revision = "0012_task_skills"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])
    op.create_index("ix_projects_owner_archived", "projects", ["owner_id", "archived_at"])

    op.create_table(
        "project_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="VIEWER"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_project_members_project_id", "project_members", ["project_id"])
    op.create_index("ix_project_members_user_id", "project_members", ["user_id"])
    op.create_index("ux_project_members_project_user", "project_members", ["project_id", "user_id"], unique=True)
    op.create_index("ix_project_members_user_role", "project_members", ["user_id", "role"])

    op.add_column("tasks", sa.Column("project_id", sa.String(36), nullable=True))
    op.add_column("tasks", sa.Column("created_by", sa.String(36), nullable=True))
    op.add_column("tasks", sa.Column("execution_kind", sa.String(16), nullable=False, server_default="task"))
    op.add_column("tasks", sa.Column("client_request_id", sa.String(64), nullable=True))
    op.create_foreign_key("fk_tasks_project_id", "tasks", "projects", ["project_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_tasks_created_by", "tasks", "users", ["created_by"], ["id"], ondelete="SET NULL")
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"])
    op.create_index("ix_tasks_created_by", "tasks", ["created_by"])
    op.create_index("ix_tasks_client_request_id", "tasks", ["client_request_id"])
    op.create_index("ux_tasks_owner_client_request", "tasks", ["owner_id", "client_request_id"], unique=True)

    connection = op.get_bind()
    users = list(connection.execute(sa.text("SELECT id FROM users")))
    for row in users:
        project_id = str(uuid.uuid4())
        member_id = str(uuid.uuid4())
        connection.execute(
            sa.text(
                "INSERT INTO projects "
                "(id, owner_id, name, description, is_pinned, created_at, updated_at) "
                "VALUES (:id, :owner, :name, '', :pinned, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"id": project_id, "owner": row.id, "name": "未归类", "pinned": True},
        )
        connection.execute(
            sa.text(
                "INSERT INTO project_members "
                "(id, project_id, user_id, role, created_at) "
                "VALUES (:id, :project, :user, 'OWNER', CURRENT_TIMESTAMP)"
            ),
            {"id": member_id, "project": project_id, "user": row.id},
        )
        connection.execute(
            sa.text(
                "UPDATE tasks SET project_id=:project, created_by=owner_id "
                "WHERE owner_id=:owner AND project_id IS NULL"
            ),
            {"project": project_id, "owner": row.id},
        )
    op.alter_column("tasks", "project_id", nullable=False)
    op.alter_column("tasks", "created_by", nullable=False)

    op.add_column("task_messages", sa.Column("author_user_id", sa.String(36), nullable=True))
    op.add_column("task_messages", sa.Column("status", sa.String(24), nullable=False, server_default="COMPLETED"))
    op.add_column("task_messages", sa.Column("client_message_id", sa.String(64), nullable=True))
    op.create_foreign_key(
        "fk_task_messages_author_user_id",
        "task_messages",
        "users",
        ["author_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ux_task_messages_task_client",
        "task_messages",
        ["task_id", "client_message_id"],
        unique=True,
    )
    connection.execute(
        sa.text(
            "UPDATE task_messages SET author_user_id = "
            "(SELECT owner_id FROM tasks WHERE tasks.id = task_messages.task_id) "
            "WHERE role = 'user' AND author_user_id IS NULL"
        )
    )

    op.add_column("artifacts", sa.Column("preview_kind", sa.String(24), nullable=False, server_default="download"))
    op.add_column("artifacts", sa.Column("inspection_status", sa.String(24), nullable=False, server_default="PENDING"))
    op.add_column("artifacts", sa.Column("preview_metadata", sa.JSON(), nullable=False, server_default="{}"))

    op.create_table(
        "project_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("relative_path", sa.String(1000), nullable=False),
        sa.Column("mime_type", sa.String(255), nullable=False, server_default="application/octet-stream"),
        sa.Column("size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("previous_version_id", sa.String(36), sa.ForeignKey("project_files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_project_files_project_id", "project_files", ["project_id"])
    op.create_index("ix_project_files_project_name", "project_files", ["project_id", "filename"])
    op.create_index("ix_project_files_project_archived", "project_files", ["project_id", "archived_at"])

    op.create_table(
        "project_memories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="ACTIVE"),
        sa.Column("source_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_project_memories_project_id", "project_memories", ["project_id"])
    op.create_index("ix_project_memories_project_status", "project_memories", ["project_id", "status"])

    op.create_table(
        "project_memory_profiles",
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "task_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.String(36), sa.ForeignKey("task_nodes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(500), nullable=False, server_default=""),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="user_url"),
        sa.Column("source_agent", sa.String(64), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_task_sources_task_id", "task_sources", ["task_id"])
    op.create_index("ix_task_sources_task_created", "task_sources", ["task_id", "created_at"])
    op.create_index("ux_task_sources_task_url", "task_sources", ["task_id", "normalized_url"], unique=True)


def downgrade():
    op.drop_table("task_sources")
    op.drop_table("project_memory_profiles")
    op.drop_table("project_memories")
    op.drop_table("project_files")

    op.drop_column("artifacts", "preview_metadata")
    op.drop_column("artifacts", "inspection_status")
    op.drop_column("artifacts", "preview_kind")

    op.drop_index("ux_task_messages_task_client", table_name="task_messages")
    op.drop_constraint("fk_task_messages_author_user_id", "task_messages", type_="foreignkey")
    op.drop_column("task_messages", "client_message_id")
    op.drop_column("task_messages", "status")
    op.drop_column("task_messages", "author_user_id")

    op.drop_index("ux_tasks_owner_client_request", table_name="tasks")
    op.drop_index("ix_tasks_client_request_id", table_name="tasks")
    op.drop_index("ix_tasks_created_by", table_name="tasks")
    op.drop_index("ix_tasks_project_id", table_name="tasks")
    op.drop_constraint("fk_tasks_created_by", "tasks", type_="foreignkey")
    op.drop_constraint("fk_tasks_project_id", "tasks", type_="foreignkey")
    op.drop_column("tasks", "client_request_id")
    op.drop_column("tasks", "execution_kind")
    op.drop_column("tasks", "created_by")
    op.drop_column("tasks", "project_id")

    op.drop_table("project_members")
    op.drop_table("projects")
