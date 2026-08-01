from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from fastapi import HTTPException

from app.agent.runner_client import RunnerClient, RunnerError
from app.models import Artifact, Task
from app.storage import resolve_task_path, task_root

try:
    import fcntl
except ImportError:  # Windows dev/test fallback: single-process no-op lock.
    fcntl = None


_OFFICE_SUFFIXES = {".docx", ".xlsx", ".pptx"}


def _valid_pdf(path: Path, *, source: Path) -> bool:
    try:
        return (
            path.is_file()
            and path.stat().st_size > 8
            and path.stat().st_mtime_ns >= source.stat().st_mtime_ns
            and path.read_bytes()[:5] == b"%PDF-"
        )
    except OSError:
        return False


@contextmanager
def _preview_lock(target: Path) -> Iterator[None]:
    """Serialize cache refreshes across API workers on the shared task volume."""

    target.parent.mkdir(parents=True, exist_ok=True)
    if fcntl is None:
        yield
        return
    lock_path = target.parent / ".preview.lock"
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def office_preview_pdf(
    task: Task,
    artifact: Artifact,
    source: Path,
    *,
    runner: RunnerClient | None = None,
    root: Path | None = None,
) -> Path:
    """Render DOCX/XLSX/PPTX into a private, non-final PDF preview cache."""

    if not source.is_file() or source.suffix.lower() not in _OFFICE_SUFFIXES:
        raise HTTPException(status_code=415, detail="仅支持 DOCX、XLSX 和 PPTX 在线预览")

    task_directory = root or task_root(task.owner_id, task.id)
    relative = f"workspace/.previews/{artifact.id}/preview.pdf"
    target = resolve_task_path(task_directory, relative, must_exist=False)
    if _valid_pdf(target, source=source):
        return target

    with _preview_lock(target):
        # Another API worker may have completed the conversion while this worker
        # was waiting for the cross-process file lock.
        if _valid_pdf(target, source=source):
            return target
        try:
            result = (runner or RunnerClient()).execute(
                user_id=task.owner_id,
                task_id=task.id,
                tool="convert_document",
                arguments={"source": artifact.relative_path, "target": relative},
                # Internal, recoverable cache refresh. It never replaces the
                # source artifact or writes into final output.
                approval_granted=True,
            )
        except RunnerError as exc:
            raise HTTPException(
                status_code=503,
                detail="Office 预览服务暂时不可用",
            ) from exc

        if not result.ok:
            raise HTTPException(
                status_code=422,
                detail=result.summary or "Office 文件无法渲染",
            )

        try:
            rendered = resolve_task_path(task_directory, relative)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(
                status_code=422,
                detail="Office 预览未生成有效 PDF",
            ) from exc
        if not _valid_pdf(rendered, source=source):
            raise HTTPException(status_code=422, detail="Office 预览 PDF 无效或不完整")
        return rendered
