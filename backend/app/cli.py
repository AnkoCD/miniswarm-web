import argparse
import getpass

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db import Base, SessionLocal, engine
from app.models import Task, TaskStatus, User, UserRole


def bootstrap_admin() -> None:
    settings = get_settings()
    username = settings.bootstrap_admin_username.strip() or "admin"
    password = settings.bootstrap_admin_password or getpass.getpass("管理员密码: ")
    if len(password) < 12:
        raise SystemExit("管理员密码至少需要 12 个字符")
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == username)):
            raise SystemExit(f"用户 {username} 已存在")
        count = db.scalar(select(func.count()).select_from(User)) or 0
        if count >= settings.max_users:
            raise SystemExit("已达到用户数量上限")
        db.add(User(username=username, password_hash=hash_password(password), role=UserRole.ADMIN))
        db.commit()
    print(f"管理员 {username} 已创建")


def requeue_queued() -> None:
    from app.worker.tasks import chat_reply_task, run_task

    with SessionLocal() as db:
        queued = list(
            db.scalars(
                select(Task)
                .where(
                    Task.status == TaskStatus.QUEUED,
                    Task.deleted_at.is_(None),
                    Task.cancel_requested.is_(False),
                )
                .order_by(Task.created_at)
            )
        )
    for task in queued:
        target = chat_reply_task if task.execution_kind == "chat" else run_task
        target.apply_async(args=[task.id], queue="control")
    print(f"已重新投递 {len(queued)} 个排队任务")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    parser.add_argument("command", choices=["bootstrap-admin", "requeue-queued"])
    args = parser.parse_args()
    if args.command == "bootstrap-admin":
        bootstrap_admin()
    elif args.command == "requeue-queued":
        requeue_queued()


if __name__ == "__main__":
    main()
