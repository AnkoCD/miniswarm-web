from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Artifact, Project, ProjectFile, Task
from app.storage import project_root, resolve_project_path, task_root


TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".json", ".xml", ".yaml", ".yml", ".log", ".html", ".htm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
OFFICE_EXTENSIONS = {".docx", ".xlsx", ".pptx"}


def validated_mime_type(path: Path, filename: str, declared: str | None) -> str:
    """Reject obvious MIME spoofing and return a stable server-side MIME type."""
    suffix = Path(filename).suffix.lower()
    header = path.read_bytes()[:512]
    expected = mimetypes.guess_type(filename)[0]
    valid_signature = True
    detected = expected or declared or "application/octet-stream"

    if suffix == ".pdf":
        valid_signature = header.startswith(b"%PDF-")
        detected = "application/pdf"
    elif suffix == ".png":
        valid_signature = header.startswith(b"\x89PNG\r\n\x1a\n")
        detected = "image/png"
    elif suffix in {".jpg", ".jpeg"}:
        valid_signature = header.startswith(b"\xff\xd8\xff")
        detected = "image/jpeg"
    elif suffix == ".gif":
        valid_signature = header.startswith((b"GIF87a", b"GIF89a"))
        detected = "image/gif"
    elif suffix == ".webp":
        valid_signature = header.startswith(b"RIFF") and header[8:12] == b"WEBP"
        detected = "image/webp"
    elif suffix in OFFICE_EXTENSIONS:
        valid_signature = header.startswith(b"PK\x03\x04")
        detected = {
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }[suffix]
    elif suffix in TEXT_EXTENSIONS | {".csv", ".tsv", ".svg"}:
        try:
            header.decode("utf-8")
        except UnicodeDecodeError:
            valid_signature = False
        detected = "text/csv" if suffix == ".csv" else (expected or "text/plain")

    if not valid_signature:
        raise HTTPException(status_code=415, detail="文件内容与扩展名不匹配")
    if declared and declared.startswith(("image/", "application/pdf")):
        declared_family = declared.split("/", 1)[0]
        detected_family = detected.split("/", 1)[0]
        if declared_family != detected_family and declared != detected:
            raise HTTPException(status_code=415, detail="文件内容与声明的 MIME 类型不匹配")
    return detected


def preview_kind(filename: str, mime_type: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".html", ".htm"} or mime_type == "text/html":
        return "html"
    if suffix == ".csv":
        return "csv"
    if suffix == ".pdf" or mime_type == "application/pdf":
        return "pdf"
    if suffix in IMAGE_EXTENSIONS or mime_type.startswith("image/"):
        return "image"
    if suffix in TEXT_EXTENSIONS or mime_type.startswith("text/"):
        return "text"
    if suffix in {".docx", ".xlsx", ".pptx"}:
        return "office"
    return "download"


def snapshot_project_files(
    db: Session,
    task: Task,
    project: Project,
    file_ids: list[str],
) -> list[Artifact]:
    if not file_ids:
        return []
    files = list(
        db.scalars(
            select(ProjectFile).where(
                ProjectFile.project_id == project.id,
                ProjectFile.id.in_(file_ids),
                ProjectFile.archived_at.is_(None),
            )
        )
    )
    if len(files) != len(set(file_ids)):
        raise HTTPException(status_code=422, detail="所选项目文件不存在或已归档")
    source_root = project_root(project.owner_id, project.id)
    destination_root = task_root(task.owner_id, task.id)
    artifacts: list[Artifact] = []
    for item in files:
        source = resolve_project_path(source_root, item.relative_path)
        target_name = item.filename
        target = destination_root / "input" / target_name
        if target.exists():
            stem, suffix = Path(item.filename).stem, Path(item.filename).suffix
            target_name = f"{stem}-v{item.version}{suffix}"
            target = destination_root / "input" / target_name
        shutil.copy2(source, target)
        artifact = Artifact(
            task_id=task.id,
            filename=target_name,
            relative_path=f"input/{target_name}",
            mime_type=item.mime_type,
            size=item.size,
            is_final=False,
            preview_kind=preview_kind(target_name, item.mime_type),
            inspection_status="READY",
            preview_metadata={
                "project_file_id": item.id,
                "project_file_version": item.version,
                "snapshot": True,
            },
        )
        db.add(artifact)
        artifacts.append(artifact)
    return artifacts
