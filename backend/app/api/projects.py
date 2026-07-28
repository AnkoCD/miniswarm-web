from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_db
from app.dependencies import get_current_user
from app.models import (
    Project,
    ProjectFile,
    ProjectMember,
    ProjectMemory,
    ProjectMemoryProfile,
    ProjectRole,
    Task,
    User,
)
from app.project_access import ensure_default_project, require_project, touch_project
from app.project_files import validated_mime_type
from app.schemas import (
    ProjectCreate,
    ProjectFileRead,
    ProjectList,
    ProjectMemberCreate,
    ProjectMemberRead,
    ProjectMemberUpdate,
    ProjectMemoryBundle,
    ProjectMemoryRead,
    ProjectMemoryUpdate,
    ProjectRead,
    ProjectUpdate,
    TaskList,
)
from app.storage import project_root, resolve_project_path, safe_filename


router = APIRouter(prefix="/projects", tags=["projects"])


def _project_read(project: Project, role: ProjectRole) -> ProjectRead:
    payload = ProjectRead.model_validate(project).model_dump()
    payload["current_user_role"] = role
    return ProjectRead(**payload)


@router.get("", response_model=ProjectList)
def list_projects(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_default_project(db, user)
    db.commit()
    query = (
        select(Project, ProjectMember.role)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user.id)
    )
    if not include_archived:
        query = query.where(Project.archived_at.is_(None))
    rows = db.execute(query.order_by(Project.is_pinned.desc(), Project.updated_at.desc())).all()
    return ProjectList(items=[_project_read(project, role) for project, role in rows], total=len(rows))


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = Project(owner_id=user.id, name=payload.name.strip(), description=payload.description.strip())
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role=ProjectRole.OWNER))
    db.add(ProjectMemoryProfile(project_id=project.id, summary=""))
    db.commit()
    db.refresh(project)
    project_root(project.owner_id, project.id)
    return _project_read(project, ProjectRole.OWNER)


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project, membership = require_project(db, project_id, user)
    return _project_read(project, membership.role)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project, membership = require_project(db, project_id, user, write=True)
    if payload.name is not None:
        project.name = payload.name.strip()
    if payload.description is not None:
        project.description = payload.description.strip()
    if payload.is_pinned is not None:
        project.is_pinned = payload.is_pinned
    touch_project(project)
    db.commit()
    db.refresh(project)
    return _project_read(project, membership.role)


@router.post("/{project_id}/archive", response_model=ProjectRead)
def archive_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project, membership = require_project(db, project_id, user, owner=True)
    project.archived_at = datetime.now(UTC)
    touch_project(project)
    db.commit()
    db.refresh(project)
    return _project_read(project, membership.role)


@router.post("/{project_id}/restore", response_model=ProjectRead)
def restore_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project, membership = require_project(
        db,
        project_id,
        user,
        owner=True,
        include_archived=True,
    )
    project.archived_at = None
    touch_project(project)
    db.commit()
    db.refresh(project)
    return _project_read(project, membership.role)


@router.get("/{project_id}/members", response_model=list[ProjectMemberRead])
def list_members(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_project(db, project_id, user)
    rows = db.execute(
        select(ProjectMember, User.username)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.created_at)
    ).all()
    return [
        ProjectMemberRead(
            id=member.id,
            project_id=member.project_id,
            user_id=member.user_id,
            username=username,
            role=member.role,
            created_at=member.created_at,
        )
        for member, username in rows
    ]


@router.post("/{project_id}/members", response_model=ProjectMemberRead, status_code=status.HTTP_201_CREATED)
def add_member(
    project_id: str,
    payload: ProjectMemberCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project, _ = require_project(db, project_id, user, owner=True)
    invited = db.scalar(select(User).where(User.username == payload.username.strip(), User.is_active.is_(True)))
    if invited is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    existing = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == invited.id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="该账号已经是项目成员")
    role = ProjectRole.EDITOR if payload.role == ProjectRole.OWNER else payload.role
    member = ProjectMember(project_id=project_id, user_id=invited.id, role=role)
    db.add(member)
    touch_project(project)
    db.commit()
    db.refresh(member)
    return ProjectMemberRead(
        id=member.id,
        project_id=project_id,
        user_id=invited.id,
        username=invited.username,
        role=member.role,
        created_at=member.created_at,
    )


@router.patch("/{project_id}/members/{member_user_id}", response_model=ProjectMemberRead)
def update_member(
    project_id: str,
    member_user_id: str,
    payload: ProjectMemberUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project, _ = require_project(db, project_id, user, owner=True)
    member = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == member_user_id,
        )
    )
    target = db.get(User, member_user_id)
    if member is None or target is None:
        raise HTTPException(status_code=404, detail="项目成员不存在")
    if member.user_id == project.owner_id:
        raise HTTPException(status_code=409, detail="不能修改项目拥有者角色")
    member.role = ProjectRole.EDITOR if payload.role == ProjectRole.OWNER else payload.role
    touch_project(project)
    db.commit()
    return ProjectMemberRead(
        id=member.id,
        project_id=project_id,
        user_id=target.id,
        username=target.username,
        role=member.role,
        created_at=member.created_at,
    )


@router.delete("/{project_id}/members/{member_user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    project_id: str,
    member_user_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project, _ = require_project(db, project_id, user, owner=True)
    if member_user_id == project.owner_id:
        raise HTTPException(status_code=409, detail="不能移除项目拥有者")
    member = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == member_user_id,
        )
    )
    if member is None:
        raise HTTPException(status_code=404, detail="项目成员不存在")
    db.delete(member)
    touch_project(project)
    db.commit()


@router.get("/{project_id}/files", response_model=list[ProjectFileRead])
def list_project_files(
    project_id: str,
    include_archived: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_project(db, project_id, user)
    query = select(ProjectFile).where(ProjectFile.project_id == project_id)
    if not include_archived:
        query = query.where(ProjectFile.archived_at.is_(None))
    return list(db.scalars(query.order_by(ProjectFile.filename, ProjectFile.version.desc())))


@router.post("/{project_id}/files", response_model=ProjectFileRead, status_code=status.HTTP_201_CREATED)
def upload_project_file(
    project_id: str,
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project, _ = require_project(db, project_id, user, write=True)
    try:
        filename = safe_filename(upload.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    used = db.scalar(
        select(func.coalesce(func.sum(ProjectFile.size), 0)).where(
            ProjectFile.project_id == project.id,
            ProjectFile.archived_at.is_(None),
        )
    ) or 0
    latest = db.scalar(
        select(ProjectFile)
        .where(ProjectFile.project_id == project.id, ProjectFile.filename == filename)
        .order_by(ProjectFile.version.desc())
    )
    version = (latest.version + 1) if latest else 1
    relative = f"files/{filename}/{version}-{uuid.uuid4().hex}/{filename}"
    root = project_root(project.owner_id, project.id)
    target = resolve_project_path(root, relative, must_exist=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".uploading")
    max_file = get_settings().max_upload_mb * 1024 * 1024
    max_project = get_settings().max_project_storage_gb * 1024 * 1024 * 1024
    size = 0
    try:
        with temporary.open("xb") as destination:
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)
                if size > max_file:
                    raise HTTPException(status_code=413, detail="上传文件超过大小限制")
                if used + size > max_project:
                    raise HTTPException(status_code=413, detail="项目文件容量已达到上限")
                destination.write(chunk)
        mime_type = validated_mime_type(temporary, filename, upload.content_type)
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    item = ProjectFile(
        project_id=project.id,
        uploaded_by=user.id,
        filename=filename,
        relative_path=relative,
        mime_type=mime_type,
        size=size,
        version=version,
        previous_version_id=latest.id if latest else None,
    )
    db.add(item)
    touch_project(project)
    db.commit()
    db.refresh(item)
    return item


@router.get("/{project_id}/files/{file_id}/download")
def download_project_file(
    project_id: str,
    file_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project, _ = require_project(db, project_id, user)
    item = db.get(ProjectFile, file_id)
    if item is None or item.project_id != project.id:
        raise HTTPException(status_code=404, detail="项目文件不存在")
    try:
        path = resolve_project_path(project_root(project.owner_id, project.id), item.relative_path)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="项目文件不存在") from exc
    return FileResponse(path, media_type=item.mime_type, filename=item.filename)


@router.post("/{project_id}/files/{file_id}/archive", response_model=ProjectFileRead)
def archive_project_file(
    project_id: str,
    file_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project, _ = require_project(db, project_id, user, write=True)
    item = db.get(ProjectFile, file_id)
    if item is None or item.project_id != project.id:
        raise HTTPException(status_code=404, detail="项目文件不存在")
    item.archived_at = item.archived_at or datetime.now(UTC)
    touch_project(project)
    db.commit()
    db.refresh(item)
    return item


@router.get("/{project_id}/memories", response_model=ProjectMemoryBundle)
def list_project_memories(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_project(db, project_id, user)
    profile = db.get(ProjectMemoryProfile, project_id)
    if profile is None:
        profile = ProjectMemoryProfile(project_id=project_id, summary="")
        db.add(profile)
        db.commit()
        db.refresh(profile)
    items = list(
        db.scalars(
            select(ProjectMemory)
            .where(ProjectMemory.project_id == project_id)
            .order_by(ProjectMemory.updated_at.desc())
        )
    )
    return ProjectMemoryBundle(profile=profile, items=items)


@router.patch("/{project_id}/memories/{memory_id}", response_model=ProjectMemoryRead)
def update_project_memory(
    project_id: str,
    memory_id: str,
    payload: ProjectMemoryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_project(db, project_id, user, write=True)
    memory = db.get(ProjectMemory, memory_id)
    if memory is None or memory.project_id != project_id:
        raise HTTPException(status_code=404, detail="项目记忆不存在")
    if payload.statement is not None:
        memory.statement = payload.statement.strip()
    if payload.category is not None:
        memory.category = payload.category.strip()
    if payload.status is not None:
        memory.status = payload.status
    memory.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(memory)
    return memory


@router.get("/{project_id}/tasks", response_model=TaskList)
def list_project_tasks(
    project_id: str,
    include_archived: bool = False,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_project(db, project_id, user)
    filters = [Task.project_id == project_id]
    if not include_archived:
        filters.append(Task.deleted_at.is_(None))
    total = db.scalar(select(func.count()).select_from(Task).where(*filters)) or 0
    items = list(
        db.scalars(
            select(Task).where(*filters).order_by(Task.created_at.desc()).offset(offset).limit(limit)
        )
    )
    return TaskList(items=items, total=total)
