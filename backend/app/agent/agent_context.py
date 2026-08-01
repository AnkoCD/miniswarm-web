from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.memory import memory_context
from app.models import (
    Project,
    ProjectMemory,
    ProjectMemoryProfile,
    Task,
    TaskBriefVersion,
    TaskMessage,
)


def isolated_agent_context(db: Session, task: Task, *, limit: int = 12) -> str:
    """Build shared task context without another Agent's model conversation.

    Each execution node receives a fresh model message list. This function keeps
    only user-authored task messages, the current brief, stable project context,
    and long-term preferences. Agent outputs flow only through explicit DAG
    dependencies and are appended separately by the executor.
    """

    latest_brief = db.scalar(
        select(TaskBriefVersion)
        .where(TaskBriefVersion.task_id == task.id)
        .order_by(TaskBriefVersion.version.desc())
        .limit(1)
    )
    user_messages = list(
        db.scalars(
            select(TaskMessage)
            .where(
                TaskMessage.task_id == task.id,
                TaskMessage.role == "user",
            )
            .order_by(TaskMessage.created_at.desc())
            .limit(limit)
        )
    )
    user_messages.reverse()

    project = db.get(Project, task.project_id) if task.project_id else None
    project_profile = (
        db.get(ProjectMemoryProfile, task.project_id) if task.project_id else None
    )
    project_memories = (
        list(
            db.scalars(
                select(ProjectMemory)
                .where(
                    ProjectMemory.project_id == task.project_id,
                    ProjectMemory.status == "ACTIVE",
                )
                .order_by(ProjectMemory.updated_at.desc())
                .limit(10)
            )
        )
        if task.project_id
        else []
    )

    lines = [
        f"原始任务：{task.prompt}",
        f"当前任务简报版本：v{task.brief_version}",
    ]
    if latest_brief is not None:
        lines.extend(
            [
                f"当前目标：{latest_brief.goal}",
                "当前验收条件："
                + ("；".join(latest_brief.acceptance_criteria) or "未单独列出"),
                f"最近变更：{latest_brief.change_summary or '无'}",
            ]
        )
    lines.extend(
        [
            "",
            "用户长期偏好（只作参考，当前明确指令优先）：",
            memory_context(db, task.owner_id) or "暂无",
            "",
            "项目背景（只读共享上下文）：",
            f"{project.name}: {project.description}" if project else "暂无",
            "项目记忆摘要：",
            project_profile.summary
            if project_profile and project_profile.summary
            else "暂无",
            "项目记忆条目：",
            "\n".join(f"- {item.statement}" for item in project_memories) or "暂无",
            "",
            "用户在本任务中的明确消息：",
        ]
    )
    for message in user_messages:
        lines.append(f"[第 {message.revision} 轮] {message.content}")
    lines.extend(
        [
            "",
            "隔离规则：不得假设看见其他并行 Agent 的内部对话、草稿或工具记录。",
            "只有执行器随后提供的依赖节点摘要和允许读取的共享文件才可作为其他 Agent 的结果。",
        ]
    )
    return "\n".join(lines)[-20_000:]
