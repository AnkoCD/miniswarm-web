from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Project, ProjectMember, ProjectMemoryProfile, ProjectRole, Task, User


WRITE_ROLES = {ProjectRole.OWNER, ProjectRole.EDITOR}


def ensure_default_project(db: Session, user: User) -> Project:
    project = db.scalar(
        select(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(
            ProjectMember.user_id == user.id,
            ProjectMember.role == ProjectRole.OWNER,
            Project.name == "未归类",
            Project.archived_at.is_(None),
        )
        .order_by(Project.created_at)
    )
    if project is not None:
        return project
    project = Project(owner_id=user.id, name="未归类", description="自动迁移和未指定项目的任务", is_pinned=True)
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role=ProjectRole.OWNER))
    db.add(ProjectMemoryProfile(project_id=project.id, summary=""))
    db.flush()
    return project


def project_membership(db: Session, project_id: str, user_id: str) -> ProjectMember | None:
    return db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )


def require_project(
    db: Session,
    project_id: str,
    user: User,
    *,
    write: bool = False,
    owner: bool = False,
    include_archived: bool = False,
) -> tuple[Project, ProjectMember]:
    project = db.get(Project, project_id)
    membership = project_membership(db, project_id, user.id) if project else None
    if project is None or membership is None or (project.archived_at is not None and not include_archived):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    if owner and membership.role != ProjectRole.OWNER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有项目拥有者可以执行此操作")
    if write and membership.role not in WRITE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前项目仅允许查看")
    return project, membership


def require_task(
    db: Session,
    task_id: str,
    user: User,
    *,
    write: bool = False,
    include_archived: bool = False,
) -> Task:
    task = db.get(Task, task_id)
    if task is None or (task.deleted_at is not None and not include_archived):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    if task.project_id:
        require_project(db, task.project_id, user, write=write, include_archived=include_archived)
    elif task.owner_id != user.id:
        # 仅为迁移前数据保留兼容；管理员也不会自动获得其他人的私人任务。
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return task


def touch_project(project: Project) -> None:
    project.updated_at = datetime.now(UTC)
