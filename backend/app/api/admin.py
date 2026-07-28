from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.db import get_db
from app.dependencies import get_admin_user
from app.models import User
from app.schemas import PasswordReset, SystemConfigRead, UserActiveUpdate, UserCreate, UserRead, WorkerStatusRead
from app.worker.celery_app import celery_app

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/system", response_model=SystemConfigRead)
def system_config(_: User = Depends(get_admin_user)):
    settings = get_settings()
    return SystemConfigRead(
        deepseek_configured=bool(settings.deepseek_api_key),
        anysearch_configured=bool(settings.anysearch_api_key),
        model_orchestrator=settings.model_orchestrator,
        model_worker=settings.model_worker,
        model_reviewer=settings.model_reviewer,
        max_users=settings.max_users,
        max_active_tasks=settings.max_active_tasks,
        max_active_tasks_per_user=settings.max_active_tasks_per_user,
        max_agents_per_task=settings.max_agents_per_task,
        max_global_agents=settings.max_global_agents,
    )


@router.get("/workers", response_model=list[WorkerStatusRead])
def worker_status(_: User = Depends(get_admin_user)):
    try:
        inspector = celery_app.control.inspect(timeout=1.0)
        pings = inspector.ping() or {}
        active = inspector.active() or {}
        reserved = inspector.reserved() or {}
    except Exception:
        return []
    names = sorted(set(pings) | set(active) | set(reserved))
    return [
        WorkerStatusRead(
            name=name,
            online=name in pings,
            active_tasks=len(active.get(name, [])),
            reserved_tasks=len(reserved.get(name, [])),
        )
        for name in names
    ]


@router.get("/users", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db), _: User = Depends(get_admin_user)):
    return list(db.scalars(select(User).order_by(User.created_at)))


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    count = db.scalar(select(func.count()).select_from(User)) or 0
    if count >= get_settings().max_users:
        raise HTTPException(status_code=409, detail="系统最多允许 3 个账号")
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(status_code=409, detail="用户名已存在")
    user = User(username=payload.username, password_hash=hash_password(payload.password), role=payload.role)
    db.add(user)
    db.commit()
    return user


@router.put("/users/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: str,
    payload: PasswordReset,
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.password_hash = hash_password(payload.new_password)
    db.commit()


@router.put("/users/{user_id}/active", response_model=UserRead)
def update_active(
    user_id: str,
    payload: UserActiveUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == admin.id and not payload.is_active:
        raise HTTPException(status_code=400, detail="不能停用当前管理员")
    user.is_active = payload.is_active
    db.commit()
    return user
