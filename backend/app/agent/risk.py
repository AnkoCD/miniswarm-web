from pathlib import Path

from app.storage import resolve_task_path


ALWAYS_APPROVAL = {
    "move_file",
    "move_to_trash",
    "search_news",
    "anysearch",
    "install_skill_from_github",
}
TARGET_ARGUMENT = {
    "write_text": "path",
    "copy_file": "target",
    "copy_skill_file": "target",
    "create_zip": "target",
    "convert_document": "target",
    "convert_to_markdown": "target",
}
YOLO_WRITABLE_ROOTS = {"workspace", "shared", "output"}


def approval_reason(tool: str, arguments: dict, root: Path) -> str | None:
    if tool in ALWAYS_APPROVAL:
        if tool == "install_skill_from_github":
            return "该操作会从 GitHub 下载第三方 Skill，并在 SkillSpector 扫描通过后安装到服务器"
        if tool in {"search_news", "anysearch"}:
            provider = "Bing News" if tool == "search_news" else "AnySearch"
            return f"该操作会把检索词或网址发送到 {provider} 并访问外部网络"
        return "该操作会移动或删除已有文件"
    target_key = TARGET_ARGUMENT.get(tool)
    if target_key:
        raw = arguments.get(target_key)
        if isinstance(raw, str):
            try:
                target = resolve_task_path(root, raw, must_exist=False)
            except ValueError:
                return "目标路径无效，需要人工确认"
            if target.exists():
                return "该操作会覆盖已有文件"
    return None


def _is_yolo_generated_path(root: Path, raw: object) -> bool:
    if not isinstance(raw, str):
        return False
    try:
        target = resolve_task_path(root, raw, must_exist=False)
        relative = target.relative_to(root)
    except (ValueError, FileNotFoundError):
        return False
    return bool(relative.parts) and relative.parts[0] in YOLO_WRITABLE_ROOTS


def yolo_auto_approvable(tool: str, arguments: dict, root: Path) -> bool:
    """Allow only bounded, recoverable operations inside generated task files."""
    if tool in {"search_news", "anysearch"}:
        return True
    if tool == "move_file":
        return _is_yolo_generated_path(root, arguments.get("source")) and _is_yolo_generated_path(
            root, arguments.get("target")
        )
    target_key = TARGET_ARGUMENT.get(tool)
    return bool(target_key) and _is_yolo_generated_path(root, arguments.get(target_key))
