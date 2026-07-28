from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import (
    Artifact,
    Project,
    ProjectFile,
    ProjectMember,
    ProjectMemory,
    Task,
    TaskMessage,
    TaskSource,
    User,
    UserMemory,
)
from app.schemas import SearchItem, SearchResult


router = APIRouter(prefix="/search", tags=["search"])


def _snippet(value: str, term: str, width: int = 180) -> str:
    clean = " ".join((value or "").split())
    index = clean.lower().find(term.lower())
    if index < 0:
        return clean[:width]
    start = max(0, index - 45)
    return clean[start : start + width]


@router.get("", response_model=SearchResult)
def search_workspace(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    term = q.strip()
    pattern = f"%{term}%"
    project_ids = list(
        db.scalars(select(ProjectMember.project_id).where(ProjectMember.user_id == user.id))
    )
    task_ids = list(db.scalars(select(Task.id).where(Task.project_id.in_(project_ids)))) if project_ids else []
    items: list[SearchItem] = []

    if project_ids:
        for project in db.scalars(
            select(Project).where(
                Project.id.in_(project_ids),
                or_(Project.name.ilike(pattern), Project.description.ilike(pattern)),
            ).limit(100)
        ):
            items.append(
                SearchItem(
                    kind="project",
                    id=project.id,
                    project_id=project.id,
                    title=project.name,
                    snippet=_snippet(project.description, term),
                    updated_at=project.updated_at,
                )
            )
        for task in db.scalars(
            select(Task).where(
                Task.project_id.in_(project_ids),
                or_(Task.title.ilike(pattern), Task.prompt.ilike(pattern)),
            ).limit(100)
        ):
            items.append(
                SearchItem(
                    kind="task",
                    id=task.id,
                    project_id=task.project_id,
                    task_id=task.id,
                    title=task.title,
                    snippet=_snippet(task.prompt, term),
                    updated_at=task.created_at,
                )
            )
        for file in db.scalars(
            select(ProjectFile).where(
                ProjectFile.project_id.in_(project_ids),
                ProjectFile.filename.ilike(pattern),
            ).limit(100)
        ):
            items.append(
                SearchItem(
                    kind="project_file",
                    id=file.id,
                    project_id=file.project_id,
                    title=file.filename,
                    snippet=f"项目文件 · v{file.version}",
                    updated_at=file.created_at,
                )
            )
        for memory in db.scalars(
            select(ProjectMemory).where(
                ProjectMemory.project_id.in_(project_ids),
                ProjectMemory.statement.ilike(pattern),
            ).limit(100)
        ):
            items.append(
                SearchItem(
                    kind="project_memory",
                    id=memory.id,
                    project_id=memory.project_id,
                    task_id=memory.source_task_id,
                    title="项目记忆",
                    snippet=_snippet(memory.statement, term),
                    updated_at=memory.updated_at,
                )
            )
    if task_ids:
        task_project = dict(
            db.execute(select(Task.id, Task.project_id).where(Task.id.in_(task_ids))).all()
        )
        for message in db.scalars(
            select(TaskMessage).where(
                TaskMessage.task_id.in_(task_ids),
                TaskMessage.content.ilike(pattern),
            ).limit(100)
        ):
            items.append(
                SearchItem(
                    kind="message",
                    id=message.id,
                    project_id=task_project.get(message.task_id),
                    task_id=message.task_id,
                    title="对话消息",
                    snippet=_snippet(message.content, term),
                    updated_at=message.created_at,
                )
            )
        for artifact in db.scalars(
            select(Artifact).where(
                Artifact.task_id.in_(task_ids),
                Artifact.filename.ilike(pattern),
            ).limit(100)
        ):
            items.append(
                SearchItem(
                    kind="artifact",
                    id=artifact.id,
                    project_id=task_project.get(artifact.task_id),
                    task_id=artifact.task_id,
                    title=artifact.filename,
                    snippet="任务产物",
                    updated_at=artifact.created_at,
                )
            )
        for source in db.scalars(
            select(TaskSource).where(
                TaskSource.task_id.in_(task_ids),
                or_(TaskSource.title.ilike(pattern), TaskSource.domain.ilike(pattern)),
            ).limit(100)
        ):
            items.append(
                SearchItem(
                    kind="source",
                    id=source.id,
                    project_id=task_project.get(source.task_id),
                    task_id=source.task_id,
                    title=source.title or source.domain,
                    snippet=source.domain,
                    updated_at=source.created_at,
                )
            )
    for memory in db.scalars(
        select(UserMemory).where(
            UserMemory.user_id == user.id,
            UserMemory.statement.ilike(pattern),
        ).limit(100)
    ):
        items.append(
            SearchItem(
                kind="global_memory",
                id=memory.id,
                task_id=memory.source_task_id,
                title="全局记忆",
                snippet=_snippet(memory.statement, term),
                updated_at=memory.updated_at,
            )
        )
    items.sort(key=lambda item: item.updated_at or datetime.min.replace(tzinfo=UTC), reverse=True)
    return SearchResult(items=items[offset : offset + limit], total=len(items), limit=limit, offset=offset)
