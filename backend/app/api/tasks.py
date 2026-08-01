import asyncio
import csv
import json
import zipfile
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
import redis.asyncio as async_redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.db import SessionLocal, get_db
from app.dependencies import get_current_user
from app.models import ApiUsage, Approval, ApprovalStatus, Artifact, MemoryExtraction, NodeStatus, ProjectFile, ProjectMember, ProjectRole, Task, TaskBriefVersion, TaskDirective, TaskEvent, TaskMessage, TaskNode, TaskSource, TaskStatus, ToolCall, User
from app.schemas import ApprovalDecision, ApprovalRead, ArchiveResponse, ArchiveTaskList, ArchiveTaskRead, ArtifactPreviewMetadata, ArtifactRead, EventList, MemoryExtractionRead, TaskCreate, TaskList, TaskMessageCreate, TaskMessageRead, TaskNodeRead, TaskRead, TaskSourceRead, TaskSupervisionRead, ToolCallRead, UsageSummary
from app.services import add_event, ensure_initial_message, global_active_task_count, user_active_task_count
from app.storage import resolve_task_path, safe_filename, task_root
from app.project_access import ensure_default_project, require_project, require_task
from app.project_files import preview_kind, snapshot_project_files, validated_mime_type
from app.sources import capture_user_urls
from app.realtime import task_channel
from app.worker.tasks import analyze_archive_memory_task, chat_reply_task, run_task, supervise_message_task
from app.agent.skill_registry import available_skill_names
from app.agent.interaction_router import resolve_interaction_mode
from app.agent.deepseek import resolve_task_model
from app.office_preview import office_preview_pdf


WEB_SEARCH_DIRECTIVE = "【联网检索】请使用可用的联网搜索工具核对最新信息，并在结论中保留可追溯来源。"


def _with_web_search_directive(content: str) -> str:
    cleaned = content.strip()
    if cleaned.startswith(WEB_SEARCH_DIRECTIVE):
        return cleaned
    return f"{WEB_SEARCH_DIRECTIVE}\n\n{cleaned}"

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _artifact_path(task: Task, artifact: Artifact) -> Path:
    return resolve_task_path(task_root(task.owner_id, task.id), artifact.relative_path)


def _office_metadata(path: Path, suffix: str) -> dict:
    try:
        with zipfile.ZipFile(path) as package:
            names = package.namelist()
            if suffix == ".docx":
                document = package.read("word/document.xml").decode("utf-8", errors="ignore")
                return {
                    "paragraphs": document.count("<w:p"),
                    "tables": document.count("<w:tbl"),
                    "sections": document.count("<w:sectPr"),
                }
            if suffix == ".pptx":
                slides = [name for name in names if name.startswith("ppt/slides/slide") and name.endswith(".xml")]
                return {"slides": len(slides), "notes": sum(name.startswith("ppt/notesSlides/") for name in names)}
            if suffix == ".xlsx":
                sheets = [name for name in names if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")]
                formulas = 0
                dimensions: list[str] = []
                for name in sheets[:50]:
                    content = package.read(name).decode("utf-8", errors="ignore")
                    formulas += content.count("<f")
                    marker = 'dimension ref="'
                    start = content.find(marker)
                    dimensions.append(content[start + len(marker) : content.find('"', start + len(marker))] if start >= 0 else "")
                return {"worksheets": len(sheets), "dimensions": dimensions, "formulas": formulas}
    except (zipfile.BadZipFile, KeyError, OSError):
        return {"error": "文件结构无法读取"}
    return {}


def _preview_metadata(artifact: Artifact, path: Path) -> tuple[str, dict]:
    kind = preview_kind(artifact.filename, artifact.mime_type)
    suffix = path.suffix.lower()
    metadata = dict(artifact.preview_metadata or {})
    if kind == "office":
        metadata.update(_office_metadata(path, suffix))
    elif kind == "csv":
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as source:
                rows = list(csv.reader(source))[:501]
            metadata.update(
                {
                    "preview_rows": min(len(rows), 500),
                    "columns": min(max((len(row) for row in rows), default=0), 50),
                    "truncated": len(rows) > 500,
                }
            )
        except (OSError, UnicodeDecodeError, csv.Error):
            metadata["error"] = "CSV 无法读取"
    return kind, metadata


def owned_task(db: Session, task_id: str, user: User) -> Task:
    return require_task(db, task_id, user, write=True)


def accessible_task(db: Session, task_id: str, user: User) -> Task:
    return require_task(db, task_id, user, include_archived=True)


def _archive_read(task: Task, extraction: MemoryExtraction | None) -> ArchiveTaskRead:
    values = TaskRead.model_validate(task).model_dump()
    values.update(
        memory_status=extraction.status if extraction else "NOT_ANALYZED",
        archive_summary=extraction.task_summary if extraction else None,
        memory_items_count=extraction.memory_items_count if extraction else 0,
        memory_last_analyzed_at=extraction.completed_at if extraction else None,
    )
    return ArchiveTaskRead(**values)


def _ensure_memory_extraction(db: Session, task: Task) -> tuple[MemoryExtraction, bool]:
    extraction = db.scalar(
        select(MemoryExtraction).where(MemoryExtraction.task_id == task.id)
    )
    if extraction is not None:
        return extraction, False
    extraction = MemoryExtraction(
        user_id=task.owner_id,
        task_id=task.id,
        status="QUEUED",
        model=get_settings().model_memory,
    )
    db.add(extraction)
    db.flush()
    return extraction, True


def _archive_task(db: Session, task: Task) -> tuple[MemoryExtraction, bool]:
    if task.deleted_at is None:
        if task.status not in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELED}:
            task.cancel_requested = True
            task.status = TaskStatus.CANCELED
            task.completed_at = datetime.now(UTC)
        add_event(db, task, "task.archived", "任务已归档", content="文件仍保留，正在整理全局记忆")
        task.deleted_at = datetime.now(UTC)
    return _ensure_memory_extraction(db, task)


@router.get("", response_model=TaskList)
def list_tasks(
    all_users: bool = False,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project_ids = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
    filters = [Task.deleted_at.is_(None), Task.project_id.in_(project_ids)]
    total = db.scalar(select(func.count()).select_from(Task).where(*filters)) or 0
    items = list(
        db.scalars(
            select(Task).where(*filters).order_by(Task.created_at.desc()).offset(offset).limit(limit)
        )
    )
    return TaskList(items=items, total=total)


@router.get("/archived", response_model=ArchiveTaskList)
def list_archived_tasks(
    q: str | None = None,
    task_type: str | None = None,
    task_status: TaskStatus | None = Query(default=None, alias="status"),
    model: str | None = None,
    execution_mode: str | None = None,
    autonomy_mode: str | None = None,
    memory_status: str | None = None,
    has_artifacts: bool | None = None,
    all_users: bool = False,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project_ids = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
    filters = [Task.deleted_at.is_not(None), Task.project_id.in_(project_ids)]
    if q:
        term = f"%{q.strip()}%"
        filters.append(or_(Task.title.ilike(term), Task.prompt.ilike(term)))
    if task_type:
        filters.append(Task.task_type == task_type)
    if task_status:
        filters.append(Task.status == task_status)
    if model:
        filters.append(Task.model_mode == model)
    if execution_mode:
        filters.append(Task.execution_mode == execution_mode)
    if autonomy_mode:
        filters.append(Task.autonomy_mode == autonomy_mode)
    if memory_status:
        if memory_status == "NOT_ANALYZED":
            filters.append(MemoryExtraction.id.is_(None))
        else:
            filters.append(MemoryExtraction.status == memory_status)
    if has_artifacts is not None:
        artifact_tasks = select(Artifact.task_id).distinct()
        filters.append(Task.id.in_(artifact_tasks) if has_artifacts else Task.id.not_in(artifact_tasks))
    base = select(Task, MemoryExtraction).outerjoin(
        MemoryExtraction, MemoryExtraction.task_id == Task.id
    ).where(*filters)
    total = db.scalar(
        select(func.count()).select_from(base.subquery())
    ) or 0
    rows = db.execute(
        base.order_by(Task.deleted_at.desc()).offset(offset).limit(limit)
    ).all()
    return ArchiveTaskList(
        items=[_archive_read(task, extraction) for task, extraction in rows],
        total=total,
    )


@router.get("/archived/{task_id}", response_model=ArchiveTaskRead)
def get_archived_task(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = accessible_task(db, task_id, user)
    if task.deleted_at is None:
        raise HTTPException(status_code=404, detail="归档任务不存在")
    extraction = db.scalar(
        select(MemoryExtraction).where(MemoryExtraction.task_id == task.id)
    )
    return _archive_read(task, extraction)


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    settings = get_settings()
    if payload.client_request_id:
        existing = db.scalar(
            select(Task).where(
                Task.owner_id == user.id,
                Task.client_request_id == payload.client_request_id,
            )
        )
        if existing is not None:
            return existing
    project = ensure_default_project(db, user) if payload.project_id is None else require_project(
        db, payload.project_id, user, write=True
    )[0]
    installed_skills = available_skill_names(settings)
    unknown_skills = sorted(set(payload.selected_skills) - installed_skills)
    if unknown_skills:
        raise HTTPException(status_code=422, detail=f"Skill 未安装：{', '.join(unknown_skills)}")
    if payload.skill_mode == "manual" and not payload.selected_skills:
        raise HTTPException(status_code=422, detail="手动模式至少选择一个 Skill")
    route = (
        resolve_interaction_mode(
            payload.prompt,
            payload.execution_kind,
            model_mode=payload.model_mode,
            settings=settings,
        )
        if payload.execution_kind == "auto"
        else None
    )
    execution_kind = route.mode if route is not None else payload.execution_kind
    if execution_kind != "chat":
        if user_active_task_count(db, user) >= settings.max_active_tasks_per_user:
            raise HTTPException(status_code=409, detail="每位用户同时只能运行一个主任务")
        if global_active_task_count(db) >= settings.max_active_tasks:
            raise HTTPException(status_code=409, detail="系统并发任务已满，请稍后再试")
    original_prompt = payload.prompt.strip()
    title = payload.title or original_prompt.splitlines()[0][:80]
    effective_prompt = (
        _with_web_search_directive(original_prompt)
        if payload.web_search and execution_kind != "chat"
        else original_prompt
    )
    queued = payload.start_immediately and execution_kind != "chat"
    task = Task(
        owner_id=user.id,
        project_id=project.id,
        created_by=user.id,
        execution_kind=execution_kind,
        client_request_id=payload.client_request_id,
        title=title,
        prompt=effective_prompt,
        task_type=payload.task_type,
        execution_mode=payload.execution_mode,
        autonomy_mode=payload.autonomy_mode,
        model_mode=payload.model_mode,
        skill_mode=payload.skill_mode,
        selected_skills=list(dict.fromkeys(payload.selected_skills)),
        status=TaskStatus.QUEUED if queued else TaskStatus.CREATED,
    )
    db.add(task)
    db.flush()
    db.add(
        TaskMessage(
            task_id=task.id,
            revision=0,
            role="user",
            mode="chat" if execution_kind == "chat" else "task",
            content=effective_prompt,
            author_user_id=user.id,
            status="COMPLETED",
            client_message_id=payload.client_request_id,
        )
    )
    if route is not None and route.usage is not None:
        db.add(
            ApiUsage(
                task_id=task.id,
                purpose="interaction_router",
                model=resolve_task_model(payload.model_mode, "worker", settings),
                prompt_tokens=route.usage.prompt_tokens,
                completion_tokens=route.usage.completion_tokens,
                cache_hit_tokens=route.usage.cache_hit_tokens,
                duration_ms=route.usage.duration_ms,
            )
        )
    capture_user_urls(db, task, original_prompt)
    snapshot_project_files(db, task, project, payload.project_file_ids)
    add_event(db, task, "task.created", "任务已创建", progress=0)
    if queued:
        add_event(db, task, "task.queued", "任务已进入队列", progress=2)
    db.commit()
    task_root(user.id, task.id)
    if queued:
        run_task.apply_async(args=[task.id], queue="control")
    elif payload.start_immediately and execution_kind == "chat":
        chat_reply_task.apply_async(
            args=[task.id, payload.web_search, original_prompt],
            queue="chat",
        )
    return task


@router.get("/{task_id}", response_model=TaskRead)
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return require_task(db, task_id, user)


@router.get("/{task_id}/messages", response_model=list[TaskMessageRead])
def list_task_messages(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = accessible_task(db, task_id, user)
    ensure_initial_message(db, task)
    db.commit()
    return list(
        db.scalars(
            select(TaskMessage)
            .where(TaskMessage.task_id == task.id)
            .order_by(TaskMessage.created_at)
        )
    )


@router.post("/{task_id}/messages", response_model=TaskMessageRead, status_code=status.HTTP_202_ACCEPTED)
def create_task_message(
    task_id: str,
    payload: TaskMessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = owned_task(db, task_id, user)
    ensure_initial_message(db, task)
    if payload.client_message_id:
        existing = db.scalar(
            select(TaskMessage).where(
                TaskMessage.task_id == task.id,
                TaskMessage.client_message_id == payload.client_message_id,
            )
        )
        if existing is not None:
            return existing
    active_execution = task.status in {
        TaskStatus.QUEUED,
        TaskStatus.PLANNING,
        TaskStatus.RUNNING,
        TaskStatus.WAITING_APPROVAL,
        TaskStatus.REVIEWING,
        TaskStatus.REWORKING,
        TaskStatus.PACKAGING,
    }
    route = None
    if payload.mode == "auto" and active_execution and task.execution_kind != "chat":
        message_mode = "supervisor"
    else:
        route = resolve_interaction_mode(
            payload.content,
            payload.mode,
            task=task,
            model_mode=task.model_mode,
            settings=get_settings(),
        )
        message_mode = route.mode
    if message_mode == "revise":
        if task.status not in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELED}:
            raise HTTPException(status_code=409, detail="任务仍在运行，完成后才能执行文件修改")
        if user_active_task_count(db, user) >= get_settings().max_active_tasks_per_user:
            raise HTTPException(status_code=409, detail="每位用户同时只能运行一个主任务")
        if global_active_task_count(db) >= get_settings().max_active_tasks:
            raise HTTPException(status_code=409, detail="系统并发任务已满，请稍后再试")
        task.current_revision += 1
        task.status = TaskStatus.QUEUED
        task.progress = 0
        task.cancel_requested = False
        task.error_message = None
        task.review_retries = 0
        task.started_at = None
        task.completed_at = None
        task.execution_kind = "revision"
    elif message_mode == "task":
        if task.status != TaskStatus.CREATED:
            raise HTTPException(status_code=409, detail="只有未运行的聊天可以升级为执行任务")
        if user_active_task_count(db, user) >= get_settings().max_active_tasks_per_user:
            raise HTTPException(status_code=409, detail="每位用户同时只能运行一个主任务")
        if global_active_task_count(db) >= get_settings().max_active_tasks:
            raise HTTPException(status_code=409, detail="系统并发任务已满，请稍后再试")
        task.execution_kind = "task"
        task.status = TaskStatus.QUEUED
    if payload.execution_mode:
        task.execution_mode = payload.execution_mode
    original_content = payload.content.strip()
    effective_content = (
        _with_web_search_directive(original_content)
        if payload.web_search and message_mode in {"revise", "task"}
        else original_content
    )
    message = TaskMessage(
        task_id=task.id,
        revision=task.current_revision,
        role="user",
        mode=message_mode,
        content=effective_content,
        author_user_id=user.id,
        status="COMPLETED",
        client_message_id=payload.client_message_id,
    )
    db.add(message)
    db.flush()
    directive = None
    if message_mode == "supervisor":
        directive = TaskDirective(task_id=task.id, message_id=message.id)
        db.add(directive)
        task.supervisor_status = "QUEUED"
    capture_user_urls(db, task, original_content)
    event_type = (
        "task.revision.queued"
        if message_mode == "revise"
        else ("task.queued" if message_mode == "task" else "message.user")
    )
    title = (
        "文件修改已进入队列"
        if message_mode == "revise"
        else ("任务已进入队列" if message_mode == "task" else "用户发送了消息")
    )
    add_event(
        db,
        task,
        event_type,
        title,
        content=message.content[:1000],
        progress=2 if message_mode in {"revise", "task"} else None,
    )
    if route is not None and route.usage is not None:
        db.add(
            ApiUsage(
                task_id=task.id,
                purpose="interaction_router",
                model=resolve_task_model(task.model_mode, "worker", get_settings()),
                prompt_tokens=route.usage.prompt_tokens,
                completion_tokens=route.usage.completion_tokens,
                cache_hit_tokens=route.usage.cache_hit_tokens,
                duration_ms=route.usage.duration_ms,
            )
        )
    db.commit()
    db.refresh(message)
    if message_mode == "supervisor" and directive is not None:
        supervise_message_task.apply_async(args=[task.id, directive.id], queue="supervisor")
    elif message_mode in {"revise", "task"}:
        run_task.apply_async(args=[task.id], queue="control")
    else:
        chat_reply_task.apply_async(
            args=[task.id, payload.web_search, original_content],
            queue="chat",
        )
    return message


@router.get("/{task_id}/supervision", response_model=TaskSupervisionRead)
def get_task_supervision(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = accessible_task(db, task_id, user)
    current_brief = db.scalar(
        select(TaskBriefVersion)
        .where(TaskBriefVersion.task_id == task.id)
        .order_by(TaskBriefVersion.version.desc())
        .limit(1)
    )
    directives = list(
        db.scalars(
            select(TaskDirective)
            .where(TaskDirective.task_id == task.id)
            .order_by(TaskDirective.created_at.desc())
            .limit(50)
        )
    )
    return TaskSupervisionRead(
        status=task.supervisor_status,
        current_brief=current_brief,
        directives=directives,
    )


@router.get("/{task_id}/nodes", response_model=list[TaskNodeRead])
def list_task_nodes(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = accessible_task(db, task_id, user)
    return list(
        db.scalars(
            select(TaskNode)
            .where(
                TaskNode.task_id == task.id,
                TaskNode.revision == task.current_revision,
            )
            .order_by(TaskNode.created_at)
        )
    )


@router.get("/{task_id}/tool-calls", response_model=list[ToolCallRead])
def list_tool_calls(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = accessible_task(db, task_id, user)
    return list(db.scalars(select(ToolCall).where(ToolCall.task_id == task.id).order_by(ToolCall.created_at)))


@router.get("/{task_id}/usage", response_model=UsageSummary)
def get_usage(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = accessible_task(db, task_id, user)
    values = db.execute(
        select(
            func.coalesce(func.sum(ApiUsage.prompt_tokens), 0),
            func.coalesce(func.sum(ApiUsage.completion_tokens), 0),
            func.coalesce(func.sum(ApiUsage.cache_hit_tokens), 0),
            func.count(ApiUsage.id),
            func.coalesce(func.sum(ApiUsage.duration_ms), 0),
        ).where(ApiUsage.task_id == task.id)
    ).one()
    return UsageSummary(
        prompt_tokens=values[0], completion_tokens=values[1], cache_hit_tokens=values[2],
        calls=values[3], duration_ms=values[4],
    )


@router.post("/{task_id}/start", response_model=TaskRead)
def start_task(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = owned_task(db, task_id, user)
    if task.status != TaskStatus.CREATED:
        raise HTTPException(status_code=409, detail="只有草稿任务可以启动")
    task.status = TaskStatus.QUEUED
    add_event(db, task, "task.queued", "任务已进入队列", progress=2)
    db.commit()
    run_task.apply_async(args=[task.id], queue="control")
    return task


@router.post("/{task_id}/chat-start", response_model=TaskRead)
def start_chat(
    task_id: str,
    web_search: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = owned_task(db, task_id, user)
    if task.execution_kind != "chat" or task.status != TaskStatus.CREATED:
        raise HTTPException(status_code=409, detail="只有聊天草稿可以启动聊天回复")
    add_event(db, task, "message.user", "用户发送了消息", content=task.prompt[:1000])
    db.commit()
    chat_reply_task.apply_async(
        args=[task.id, web_search, task.prompt.strip()],
        queue="chat",
    )
    return task


@router.post("/{task_id}/files", response_model=ArtifactRead, status_code=status.HTTP_201_CREATED)
def upload_task_file(
    task_id: str,
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = owned_task(db, task_id, user)
    if task.status != TaskStatus.CREATED:
        raise HTTPException(status_code=409, detail="只能给尚未启动的草稿任务上传文件")
    try:
        filename = safe_filename(upload.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    root = task_root(task.owner_id, task.id)
    target = root / "input" / filename
    if target.exists():
        raise HTTPException(status_code=409, detail="同名文件已存在，不会自动覆盖")
    temp = root / "input" / f".{filename}.uploading"
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    size = 0
    try:
        with temp.open("xb") as destination:
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(status_code=413, detail="上传文件超过大小限制")
                destination.write(chunk)
        mime_type = validated_mime_type(temp, filename, upload.content_type)
        temp.replace(target)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    artifact = Artifact(
        task_id=task.id,
        filename=filename,
        relative_path=f"input/{filename}",
        mime_type=mime_type,
        size=size,
        is_final=False,
        preview_kind=preview_kind(filename, mime_type),
        inspection_status="READY",
    )
    db.add(artifact)
    add_event(db, task, "file.uploaded", f"已上传 {filename}", content=f"{size} bytes")
    db.commit()
    return artifact


@router.get("/{task_id}/artifacts", response_model=list[ArtifactRead])
def list_artifacts(
    task_id: str,
    final_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = accessible_task(db, task_id, user)
    query = select(Artifact).where(Artifact.task_id == task.id)
    if final_only:
        query = query.where(Artifact.is_final.is_(True))
    return list(db.scalars(query.order_by(Artifact.created_at)))


@router.get("/{task_id}/artifacts/{artifact_id}/download")
def download_artifact(
    task_id: str,
    artifact_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = accessible_task(db, task_id, user)
    artifact = db.get(Artifact, artifact_id)
    if artifact is None or artifact.task_id != task.id:
        raise HTTPException(status_code=404, detail="文件不存在")
    root = task_root(task.owner_id, task.id)
    try:
        path = resolve_task_path(root, artifact.relative_path)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="文件不存在") from exc
    return FileResponse(path, media_type=artifact.mime_type, filename=artifact.filename)


@router.get("/{task_id}/artifacts/{artifact_id}/preview")
def preview_artifact(
    task_id: str,
    artifact_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = accessible_task(db, task_id, user)
    artifact = db.get(Artifact, artifact_id)
    if artifact is None or artifact.task_id != task.id:
        raise HTTPException(status_code=404, detail="文件不存在")
    if not (artifact.mime_type.startswith("text/") or artifact.mime_type in {"application/json", "application/xml"}):
        raise HTTPException(status_code=415, detail="此文件类型不支持文本预览")
    if artifact.size > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件过大，无法在线预览")
    root = task_root(task.owner_id, task.id)
    try:
        path = resolve_task_path(root, artifact.relative_path)
        content = path.read_text(encoding="utf-8")
    except (ValueError, FileNotFoundError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=422, detail="文件无法预览") from exc
    return PlainTextResponse(content, media_type=f"{artifact.mime_type}; charset=utf-8")


@router.get("/{task_id}/artifacts/{artifact_id}/preview-metadata", response_model=ArtifactPreviewMetadata)
def artifact_preview_metadata(
    task_id: str,
    artifact_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = accessible_task(db, task_id, user)
    artifact = db.get(Artifact, artifact_id)
    if artifact is None or artifact.task_id != task.id:
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        path = _artifact_path(task, artifact)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="文件不存在") from exc
    kind, metadata = _preview_metadata(artifact, path)
    if kind == "office":
        rendered_preview = office_preview_pdf(task, artifact, path)
        metadata.update(
            {
                "rendered_preview": "pdf",
                "preview_size": rendered_preview.stat().st_size,
            }
        )
    artifact.preview_kind = kind
    artifact.preview_metadata = metadata
    if "error" in metadata:
        artifact.inspection_status = "FAILED"
    elif artifact.inspection_status != "VERIFIED":
        artifact.inspection_status = "READY"
    db.commit()
    return ArtifactPreviewMetadata(kind=kind, mime_type=artifact.mime_type, size=artifact.size, metadata=metadata)


@router.get("/{task_id}/artifacts/{artifact_id}/inline")
def inline_artifact(
    task_id: str,
    artifact_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = accessible_task(db, task_id, user)
    artifact = db.get(Artifact, artifact_id)
    if artifact is None or artifact.task_id != task.id:
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        path = _artifact_path(task, artifact)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="文件不存在") from exc
    kind = preview_kind(artifact.filename, artifact.mime_type)
    if kind == "csv":
        if artifact.size > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="CSV 过大，无法在线预览")
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as source:
                reader = csv.reader(source)
                rows = [[cell for cell in row[:50]] for _, row in zip(range(500), reader)]
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            raise HTTPException(status_code=422, detail="CSV 无法预览") from exc
        return JSONResponse({"rows": rows, "max_rows": 500, "max_columns": 50})
    if kind in {"text", "html"}:
        if artifact.size > 2 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="文件过大，无法在线预览")
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=422, detail="文件无法预览") from exc
        # HTML 由前端放入无权限 sandbox 的 srcdoc 中渲染；这里始终按纯文本返回，
        # 避免直接访问接口时执行产物内的脚本或表单。
        return PlainTextResponse(content, media_type="text/plain; charset=utf-8")
    if kind in {"image", "pdf"}:
        return FileResponse(
            path,
            media_type=artifact.mime_type,
            filename=artifact.filename,
            content_disposition_type="inline",
            headers={
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, max-age=60",
            },
        )
    if kind == "office":
        rendered = office_preview_pdf(task, artifact, path)
        return FileResponse(
            rendered,
            media_type="application/pdf",
            filename=f"{Path(artifact.filename).stem}-preview.pdf",
            content_disposition_type="inline",
            headers={
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, max-age=60",
            },
        )
    raise HTTPException(status_code=415, detail="此文件类型不支持内嵌预览")


@router.get("/{task_id}/sources", response_model=list[TaskSourceRead])
def list_task_sources(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = accessible_task(db, task_id, user)
    return list(
        db.scalars(
            select(TaskSource)
            .where(TaskSource.task_id == task.id)
            .order_by(TaskSource.created_at)
        )
    )


@router.post("/{task_id}/cancel", response_model=TaskRead)
def cancel_task(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = owned_task(db, task_id, user)
    if task.status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELED}:
        raise HTTPException(status_code=409, detail="任务已结束")
    task.cancel_requested = True
    task.status = TaskStatus.CANCELING
    add_event(db, task, "task.canceling", "正在请求取消")
    db.commit()
    return task


@router.post("/{task_id}/retry", response_model=TaskRead)
def retry_task(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = owned_task(db, task_id, user)
    if task.status not in {TaskStatus.FAILED, TaskStatus.CANCELED}:
        raise HTTPException(status_code=409, detail="只有失败或取消的任务可以重试")
    task.current_revision += 1
    task.status = TaskStatus.QUEUED
    task.progress = 0
    task.cancel_requested = False
    task.error_message = None
    task.review_retries = 0
    task.started_at = None
    task.completed_at = None
    add_event(db, task, "task.queued", "任务已重新进入队列", progress=2)
    db.commit()
    run_task.apply_async(args=[task.id], queue="control")
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_task(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = owned_task(db, task_id, user)
    extraction, created = _archive_task(db, task)
    db.commit()
    if created:
        analyze_archive_memory_task.apply_async(args=[extraction.id], queue="memory")


@router.post("/{task_id}/archive", response_model=ArchiveResponse, status_code=status.HTTP_202_ACCEPTED)
def archive_task_with_memory(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = accessible_task(db, task_id, user)
    extraction, created = _archive_task(db, task)
    db.commit()
    db.refresh(task)
    db.refresh(extraction)
    if created:
        analyze_archive_memory_task.apply_async(args=[extraction.id], queue="memory")
    return ArchiveResponse(
        task=TaskRead.model_validate(task),
        memory_extraction_id=extraction.id,
        memory_status=extraction.status,
    )


@router.post("/{task_id}/restore", response_model=TaskRead)
def restore_archived_task(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = accessible_task(db, task_id, user)
    if task.deleted_at is None:
        raise HTTPException(status_code=409, detail="任务未归档")
    task.deleted_at = None
    add_event(db, task, "task.restored", "任务已从归档恢复")
    db.commit()
    db.refresh(task)
    return task


@router.get("/{task_id}/archive-analysis", response_model=MemoryExtractionRead)
def get_archive_analysis(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = accessible_task(db, task_id, user)
    extraction = db.scalar(
        select(MemoryExtraction).where(MemoryExtraction.task_id == task.id)
    )
    if extraction is None:
        raise HTTPException(status_code=404, detail="该任务尚未进行归档分析")
    return extraction


@router.post("/{task_id}/archive-analysis/retry", response_model=MemoryExtractionRead)
def retry_archive_analysis(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = accessible_task(db, task_id, user)
    if task.deleted_at is None:
        raise HTTPException(status_code=409, detail="只有归档任务可以整理全局记忆")
    extraction, _ = _ensure_memory_extraction(db, task)
    if extraction.status in {"QUEUED", "RUNNING"}:
        raise HTTPException(status_code=409, detail="归档分析正在进行")
    extraction.status = "QUEUED"
    extraction.error_message = None
    extraction.started_at = None
    extraction.completed_at = None
    db.commit()
    db.refresh(extraction)
    analyze_archive_memory_task.apply_async(args=[extraction.id], queue="memory")
    return extraction


@router.get("/{task_id}/events", response_model=EventList)
def get_events(
    task_id: str,
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = accessible_task(db, task_id, user)
    items = list(
        db.scalars(
            select(TaskEvent)
            .where(TaskEvent.task_id == task.id, TaskEvent.id > after_id)
            .order_by(TaskEvent.id)
            .limit(limit)
        )
    )
    return EventList(items=items, last_event_id=items[-1].id if items else after_id)


@router.get("/{task_id}/approvals", response_model=list[ApprovalRead])
def list_approvals(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = accessible_task(db, task_id, user)
    return list(
        db.scalars(
            select(Approval).where(Approval.task_id == task.id).order_by(Approval.requested_at.desc())
        )
    )


@router.post("/{task_id}/approvals/{approval_id}", response_model=ApprovalRead)
def decide_approval(
    task_id: str,
    approval_id: str,
    payload: ApprovalDecision,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = owned_task(db, task_id, user)
    approval = db.get(Approval, approval_id)
    if approval is None or approval.task_id != task.id:
        raise HTTPException(status_code=404, detail="审批请求不存在")
    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=409, detail="审批请求已处理")
    approval.status = {
        "deny": ApprovalStatus.DENIED,
        "allow_once": ApprovalStatus.APPROVED_ONCE,
        "allow_for_task": ApprovalStatus.APPROVED_FOR_TASK,
    }[payload.decision]
    approval.decided_at = datetime.now(UTC)
    approval.decided_by = user.id
    if approval.tool_call_id:
        tool_call = db.get(ToolCall, approval.tool_call_id)
        node = db.get(TaskNode, tool_call.node_id) if tool_call and tool_call.node_id else None
        if node and node.status == NodeStatus.WAITING:
            node.status = NodeStatus.READY
    task.status = TaskStatus.QUEUED
    event_type = "approval.denied" if payload.decision == "deny" else "approval.approved"
    title = "风险操作已拒绝" if payload.decision == "deny" else "风险操作已批准"
    add_event(db, task, event_type, title, content=approval.summary)
    db.commit()
    run_task.apply_async(args=[task.id], queue="control")
    return approval


@router.get("/{task_id}/stream")
async def stream_events(
    task_id: str,
    request: Request,
    last_event_id: int | None = Query(default=None, ge=0),
    header_last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    accessible_task(db, task_id, user)
    try:
        cursor = last_event_id if last_event_id is not None else int(header_last_event_id or 0)
    except ValueError:
        cursor = 0

    async def generate() -> AsyncGenerator[str, None]:
        nonlocal cursor
        idle_ticks = 0
        redis_client = async_redis.from_url(get_settings().redis_url, decode_responses=True)
        pubsub = redis_client.pubsub()
        realtime_available = True
        try:
            try:
                await pubsub.subscribe(task_channel(task_id))
            except RedisError:
                realtime_available = False
            while not await request.is_disconnected():
                with SessionLocal() as stream_db:
                    events = list(
                        stream_db.scalars(
                            select(TaskEvent)
                            .where(TaskEvent.task_id == task_id, TaskEvent.id > cursor)
                            .order_by(TaskEvent.id)
                            .limit(200)
                        )
                    )
                if events:
                    idle_ticks = 0
                    for event in events:
                        cursor = event.id
                        payload = {
                            "id": event.id,
                            "task_id": event.task_id,
                            "type": event.event_type,
                            "title": event.title,
                            "content": event.content,
                            "progress": event.progress,
                            "created_at": event.created_at.isoformat(),
                        }
                        yield f"id: {event.id}\nevent: {event.event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                live = None
                if realtime_available:
                    try:
                        live = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
                    except RedisError:
                        realtime_available = False
                if live and live.get("data"):
                    try:
                        payload = json.loads(live["data"])
                    except (TypeError, ValueError):
                        payload = None
                    if payload and payload.get("type"):
                        event_type = payload["type"]
                        yield f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                        idle_ticks = 0
                else:
                    idle_ticks += 1
                    if idle_ticks % 15 == 0:
                        yield ": keep-alive\n\n"
                    if not realtime_available:
                        await asyncio.sleep(1)
        finally:
            try:
                await pubsub.close()
                await redis_client.close()
            except RedisError:
                pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
