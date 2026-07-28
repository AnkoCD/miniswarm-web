from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.memory import rebuild_profile
from app.models import MemoryRevision, User, UserMemory, UserMemoryProfile, UserRole
from app.schemas import (
    UserMemoryList,
    UserMemoryProfileRead,
    UserMemoryRead,
    UserMemoryUpdate,
)


router = APIRouter(prefix="/memories", tags=["memories"])


def _target_user_id(requested: str | None, user: User) -> str:
    if requested and requested != user.id:
        if user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="无权查看其他用户的记忆")
        return requested
    return user.id


def _owned_memory(db: Session, memory_id: str, user: User) -> UserMemory:
    memory = db.get(UserMemory, memory_id)
    if memory is None or (memory.user_id != user.id and user.role != UserRole.ADMIN):
        raise HTTPException(status_code=404, detail="记忆不存在")
    return memory


@router.get("", response_model=UserMemoryList)
def list_memories(
    memory_status: str | None = Query(default=None, alias="status"),
    category: str | None = None,
    q: str | None = None,
    user_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    owner_id = _target_user_id(user_id, user)
    filters = [UserMemory.user_id == owner_id]
    if memory_status:
        filters.append(UserMemory.status == memory_status.upper())
    if category:
        filters.append(UserMemory.category == category)
    if q:
        filters.append(UserMemory.statement.ilike(f"%{q.strip()}%"))
    total = db.scalar(select(func.count()).select_from(UserMemory).where(*filters)) or 0
    items = list(
        db.scalars(
            select(UserMemory)
            .where(*filters)
            .order_by(UserMemory.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    return UserMemoryList(items=items, total=total)


@router.get("/profile", response_model=UserMemoryProfileRead)
def get_memory_profile(
    user_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    owner_id = _target_user_id(user_id, user)
    profile = db.get(UserMemoryProfile, owner_id)
    if profile is None:
        profile = rebuild_profile(db, owner_id)
        db.commit()
        db.refresh(profile)
    return profile


@router.patch("/{memory_id}", response_model=UserMemoryRead)
def update_memory(
    memory_id: str,
    payload: UserMemoryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    memory = _owned_memory(db, memory_id, user)
    before = {
        "statement": memory.statement,
        "category": memory.category,
        "confidence": memory.confidence,
        "status": memory.status,
    }
    if payload.statement is not None:
        memory.statement = payload.statement.strip()
    if payload.category is not None:
        memory.category = payload.category
    if payload.confidence is not None:
        memory.confidence = payload.confidence
    memory.updated_at = datetime.now(UTC)
    db.add(
        MemoryRevision(
            memory_id=memory.id,
            user_id=memory.user_id,
            source_task_id=memory.source_task_id,
            action="EDITED",
            before_json=before,
            after_json={
                "statement": memory.statement,
                "category": memory.category,
                "confidence": memory.confidence,
                "status": memory.status,
            },
        )
    )
    rebuild_profile(db, memory.user_id)
    db.commit()
    db.refresh(memory)
    return memory


def _change_status(
    db: Session,
    memory: UserMemory,
    new_status: str,
    action: str,
) -> UserMemory:
    old_status = memory.status
    memory.status = new_status
    memory.updated_at = datetime.now(UTC)
    db.add(
        MemoryRevision(
            memory_id=memory.id,
            user_id=memory.user_id,
            source_task_id=memory.source_task_id,
            action=action,
            before_json={"status": old_status},
            after_json={"status": new_status},
        )
    )
    rebuild_profile(db, memory.user_id)
    db.commit()
    db.refresh(memory)
    return memory


@router.post("/{memory_id}/activate", response_model=UserMemoryRead)
def activate_memory(
    memory_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _change_status(db, _owned_memory(db, memory_id, user), "ACTIVE", "ACTIVATED")


@router.post("/{memory_id}/disable", response_model=UserMemoryRead)
def disable_memory(
    memory_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _change_status(db, _owned_memory(db, memory_id, user), "DISABLED", "DISABLED")
