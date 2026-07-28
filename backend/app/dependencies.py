from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import SESSION_COOKIE_NAME, decode_access_token
from app.db import get_db
from app.models import User, UserRole


def get_current_user(
    miniswarm_access_token: str | None = Cookie(
        default=None, alias=SESSION_COOKIE_NAME
    ),
    db: Session = Depends(get_db),
) -> User:
    if not miniswarm_access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    user_id = decode_access_token(miniswarm_access_token)
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效")
    return user


def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user
