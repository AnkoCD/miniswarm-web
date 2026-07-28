import re
from pathlib import Path

from app.core.config import Settings, get_settings


SAFE_FILENAME = re.compile(r"^[^\x00-\x1f<>:\"/\\|?*]{1,255}$")


def task_root(owner_id: str, task_id: str, settings: Settings | None = None) -> Path:
    config = settings or get_settings()
    root = (config.data_root / "users" / owner_id / "tasks" / task_id).resolve(strict=False)
    base = config.data_root.resolve(strict=False)
    try:
        root.relative_to(base)
    except ValueError as exc:
        raise ValueError("任务目录越界") from exc
    for name in ("input", "workspace", "shared", "output", "logs", "trash"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def project_root(owner_id: str, project_id: str, settings: Settings | None = None) -> Path:
    config = settings or get_settings()
    root = (config.data_root / "users" / owner_id / "projects" / project_id).resolve(strict=False)
    base = config.data_root.resolve(strict=False)
    try:
        root.relative_to(base)
    except ValueError as exc:
        raise ValueError("项目目录越界") from exc
    (root / "files").mkdir(parents=True, exist_ok=True)
    return root


def resolve_project_path(root: Path, relative_path: str, *, must_exist: bool = True) -> Path:
    target = (root / relative_path).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("项目文件路径越界") from exc
    if must_exist and (not target.exists() or not target.is_file()):
        raise FileNotFoundError(relative_path)
    return target


def safe_filename(value: str | None) -> str:
    name = (value or "").strip()
    if name in {"", ".", ".."} or not SAFE_FILENAME.fullmatch(name):
        raise ValueError("文件名无效")
    return name


def resolve_task_path(root: Path, relative_path: str, *, must_exist: bool = True) -> Path:
    target = (root / relative_path).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("文件路径越界") from exc
    if must_exist and (not target.exists() or not target.is_file()):
        raise FileNotFoundError(relative_path)
    return target
