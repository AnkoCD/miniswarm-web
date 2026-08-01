from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Artifact, Task, TaskNode, TaskSource, ToolCall, ToolCallStatus
from app.storage import resolve_task_path, task_root


FORMAT_RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("PPTX", (".pptx",), r"(?:(?<![a-z0-9])pptx?(?![a-z0-9])|powerpoint|演示文稿|幻灯片)"),
    ("DOCX", (".docx",), r"(?:(?<![a-z0-9])docx?(?![a-z0-9])|(?<![a-z0-9])word(?![a-z0-9])|word文档)"),
    ("XLSX", (".xlsx", ".xlsm"), r"(?:(?<![a-z0-9])xlsx?(?![a-z0-9])|(?<![a-z0-9])excel(?![a-z0-9])|电子表格)"),
    ("PDF", (".pdf",), r"(?:(?<![a-z0-9])pdf(?![a-z0-9]))"),
    ("CSV", (".csv",), r"(?:(?<![a-z0-9])csv(?![a-z0-9]))"),
    ("HTML", (".html", ".htm"), r"(?:(?<![a-z0-9])html(?![a-z0-9])|\.html(?![a-z0-9]))"),
    ("ZIP", (".zip",), r"(?:(?<![a-z0-9])zip(?![a-z0-9])|压缩包)"),
    ("Markdown", (".md",), r"(?:(?<![a-z0-9])markdown(?![a-z0-9])|\.md(?![a-z0-9]))"),
    ("TXT", (".txt",), r"(?:(?<![a-z0-9])txt(?![a-z0-9])|文本文件)"),
)

INSPECTABLE_SUFFIXES = {
    ".docx", ".xlsx", ".xlsm", ".pptx", ".pdf",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff",
    ".html", ".htm", ".csv", ".json", ".xml", ".yaml", ".yml",
    ".md", ".txt", ".py", ".js", ".ts", ".css", ".zip",
}

FORMAT_NEGATION = re.compile(
    r"(?:不要|无需|无须|不需要|禁止|不得|不可|不能)"
    r"[^，。；;]{0,48}$",
    re.IGNORECASE,
)
FORMAT_NEGATION_OVERRIDE = re.compile(
    r"(?:而要|但要|改为|改成|转为|(?<!不)需要|必须|应当|请)\s*"
    r"(?:生成|创建|制作|输出|导出|提供|交付)?[^，。；;]{0,24}$",
    re.IGNORECASE,
)
FORMAT_INTENT = re.compile(
    r"(?:生成|创建|制作|输出|导出|交付|提供|需要|必须|要求|命名为|保存为|格式为|"
    r"请给|给我|我要|希望得到|"
    r"generate|create|export|deliver|output|save\s+as|must|need)",
    re.IGNORECASE,
)
FORMAT_CLAUSE_BOUNDARIES = "，。；;！？!?\n\r"
REALTIME_RESEARCH = re.compile(
    r"(?:实时|最新|今日|今天|新闻|latest|recent|up-to-date)",
    re.IGNORECASE,
)
WEB_RESEARCH = re.compile(
    r"(?:(?:联网|网络|网上|网页|web).{0,12}(?:搜索|检索|查询|调研|研究)|"
    r"(?:搜索|检索|调研|研究|查找).{0,12}(?:资料|来源|数据|新闻|市场|行业|政策|论文|网页))",
    re.IGNORECASE,
)
DEEP_RESEARCH = re.compile(
    r"(?:深度调研|深入研究|研究报告|调研报告|行业分析|市场分析|竞品分析|全面调研|"
    r"deep research|in-depth research)",
    re.IGNORECASE,
)
DEFAULT_XLSX = re.compile(
    r"(?:制作|生成|创建|整理|汇总|分析).{0,24}"
    r"(?:预算表|清单|台账|统计表|数据报表|跟踪表|排期表|名单)",
    re.IGNORECASE,
)
DEFAULT_DOCX = re.compile(
    r"(?:制作|生成|创建|编写|撰写|整理).{0,24}"
    r"(?:报告|方案|合同|通知|会议纪要|简历|说明书|手册|公文|申请书|总结)",
    re.IGNORECASE,
)


@dataclass
class DeliveryGateResult:
    producer_issues: list[str] = field(default_factory=list)
    reviewer_issues: list[str] = field(default_factory=list)
    verified_paths: set[str] = field(default_factory=set)

    @property
    def passed(self) -> bool:
        return not self.producer_issues and not self.reviewer_issues

    @property
    def summary(self) -> str:
        return "；".join([*self.producer_issues, *self.reviewer_issues])


def requested_formats(prompt: str) -> list[tuple[str, tuple[str, ...]]]:
    normalized = prompt.lower()
    results: list[tuple[str, tuple[str, ...]]] = []
    matched_labels = sum(
        bool(re.search(pattern, normalized, re.IGNORECASE))
        for _, _, pattern in FORMAT_RULES
    )
    for label, suffixes, pattern in FORMAT_RULES:
        matches = list(re.finditer(pattern, normalized, re.IGNORECASE))
        requested = False
        for match in matches:
            clause_start = max(
                (normalized.rfind(mark, 0, match.start()) for mark in FORMAT_CLAUSE_BOUNDARIES),
                default=-1,
            ) + 1
            clause_end_candidates = [
                position
                for mark in FORMAT_CLAUSE_BOUNDARIES
                if (position := normalized.find(mark, match.end())) >= 0
            ]
            clause_end = min(clause_end_candidates, default=len(normalized))
            clause = normalized[clause_start:clause_end]
            prefix = normalized[clause_start:match.start()]
            negated = bool(
                FORMAT_NEGATION.search(prefix)
                and not FORMAT_NEGATION_OVERRIDE.search(prefix)
            )
            explicit_extension = (
                match.start() > 0 and normalized[match.start() - 1] == "."
            )
            short_direct_request = (
                matched_labels == 1 and len(normalized.strip()) <= 24
            )
            if (
                not negated
                and (
                    explicit_extension
                    or FORMAT_INTENT.search(prefix[-32:])
                    or short_direct_request
                )
            ):
                requested = True
                break
        if requested:
            results.append((label, suffixes))
    web_creation = re.search(
        r"(?:(?:生成|制作|创建|开发|构建|设计|编写).{0,24}(?:网页|网站|webpage|website)|"
        r"(?:网页|网站|webpage|website).{0,24}(?:生成|制作|创建|开发|构建|设计|编写))",
        normalized,
        re.IGNORECASE,
    )
    if web_creation and not any(label == "HTML" for label, _ in results):
        results.append(("HTML", (".html", ".htm")))
    if not results and DEFAULT_XLSX.search(normalized):
        results.append(("XLSX", (".xlsx", ".xlsm")))
    elif not results and DEFAULT_DOCX.search(normalized):
        results.append(("DOCX", (".docx",)))
    return results


def is_requested_delivery_artifact(prompt: str, filename: str) -> bool:
    """Return whether an output file is a user-requested delivery format.

    When the user names one or more formats, conversions and render previews in
    other formats remain useful working artifacts but must not block delivery.
    Tasks without an explicit/default format keep the historical behavior and
    treat every output file as deliverable.
    """
    formats = requested_formats(prompt)
    if not formats:
        return True
    suffix = Path(filename).suffix.lower()
    return any(suffix in accepted for _, accepted in formats)


def requires_file_output(task: Task, formats: list[tuple[str, tuple[str, ...]]]) -> bool:
    if formats or task.task_type in {"document", "code", "data", "file"}:
        return True
    return bool(
        re.search(
            r"(?:生成|制作|创建|输出|导出|开发|构建|编写|修改).{0,30}"
            r"(?:文件|报告|文档|代码|网页|网站|表格|图表|演示)",
            task.prompt,
            re.IGNORECASE,
        )
    )


def _normalized_tool_path(raw: object) -> str:
    if not isinstance(raw, str):
        return ""
    value = raw.replace("\\", "/").strip()
    while value.startswith("./"):
        value = value[2:]
    return value


def source_requirements(prompt: str) -> tuple[int, int, bool]:
    if DEEP_RESEARCH.search(prompt):
        return 4, 3, True
    if REALTIME_RESEARCH.search(prompt):
        return 2, 2, False
    if WEB_RESEARCH.search(prompt):
        require_extract = bool(
            re.search(r"(?:报告|分析|对比|调研|研究|report|analysis)", prompt, re.IGNORECASE)
        )
        return 2, 2, require_extract
    return 0, 0, False


def _artifact_source_domains(path: Path, expected_domains: set[str]) -> set[str]:
    if not expected_domains:
        return set()
    suffix = path.suffix.lower()
    text = ""
    try:
        if suffix in {".docx", ".xlsx", ".xlsm", ".pptx", ".zip"}:
            with zipfile.ZipFile(path) as archive:
                chunks: list[bytes] = []
                total = 0
                for item in archive.infolist():
                    if item.is_dir() or item.file_size > 5_000_000:
                        continue
                    if not item.filename.lower().endswith(
                        (".xml", ".rels", ".txt", ".md", ".csv", ".html", ".htm")
                    ):
                        continue
                    if total + item.file_size > 15_000_000:
                        break
                    chunks.append(archive.read(item))
                    total += item.file_size
                text = b"\n".join(chunks).decode("utf-8", errors="ignore")
        elif suffix == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(path)
            parts: list[str] = []
            for page in reader.pages[:100]:
                parts.append(page.extract_text() or "")
                annotations = page.get("/Annots") or []
                for reference in annotations:
                    try:
                        annotation = reference.get_object()
                        action = annotation.get("/A")
                        if action and action.get("/URI"):
                            parts.append(str(action.get("/URI")))
                    except (AttributeError, TypeError):
                        continue
            text = "\n".join(parts)
        elif suffix in {
            ".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml",
            ".html", ".htm",
        }:
            if path.stat().st_size <= 10_000_000:
                text = path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, ValueError, zipfile.BadZipFile):
        return set()
    lowered = text.casefold()
    return {domain for domain in expected_domains if domain.casefold() in lowered}


def validate_delivery(
    db: Session,
    task: Task,
    nodes: list[TaskNode],
) -> DeliveryGateResult:
    result = DeliveryGateResult()
    artifacts = list(
        db.scalars(
            select(Artifact)
            .where(Artifact.task_id == task.id, Artifact.is_final.is_(True))
            .order_by(Artifact.created_at)
        )
    )
    formats = requested_formats(task.prompt)
    if requires_file_output(task, formats) and not artifacts:
        result.producer_issues.append("任务要求交付文件，但 output 中没有最终文件")

    suffixes = {Path(item.filename).suffix.lower() for item in artifacts}
    for label, accepted in formats:
        if not suffixes.intersection(accepted):
            result.producer_issues.append(
                f"用户要求 {label}，但没有生成 {', '.join(accepted)} 文件"
            )

    root = task_root(task.owner_id, task.id, get_settings())
    valid_artifacts: list[Artifact] = []
    for artifact in artifacts:
        try:
            path = resolve_task_path(root, artifact.relative_path)
        except (ValueError, FileNotFoundError):
            result.producer_issues.append(f"交付文件不存在：{artifact.filename}")
            continue
        actual_size = path.stat().st_size
        if actual_size <= 0:
            result.producer_issues.append(f"交付文件为空：{artifact.filename}")
            continue
        if artifact.size != actual_size:
            artifact.size = actual_size
        valid_artifacts.append(artifact)

    minimum_sources, minimum_domains, require_extract = source_requirements(task.prompt)
    source_domains: set[str] = set()
    if minimum_sources:
        sources = list(
            db.scalars(
                select(TaskSource).where(TaskSource.task_id == task.id)
            )
        )
        searched_sources = [
            source for source in sources if source.source_type != "user_url"
        ]
        source_domains = {source.domain for source in searched_sources if source.domain}
        if len(searched_sources) < minimum_sources:
            result.producer_issues.append(
                f"网络调研至少需要 {minimum_sources} 条可追溯来源，当前只有 {len(searched_sources)} 条"
            )
        if len(source_domains) < minimum_domains:
            result.producer_issues.append(
                f"网络调研至少需要 {minimum_domains} 个独立来源域名，当前只有 {len(source_domains)} 个"
            )
        if require_extract:
            extracted = db.scalar(
                select(ToolCall.id).where(
                    ToolCall.task_id == task.id,
                    ToolCall.status == ToolCallStatus.SUCCEEDED,
                    ToolCall.tool_name == "anysearch",
                    ToolCall.arguments["action"].as_string() == "extract",
                ).limit(1)
            )
            if extracted is None:
                result.producer_issues.append(
                    "深度网络调研尚未使用 AnySearch extract 阅读主要来源正文"
                )
        if valid_artifacts and source_domains:
            cited_domains: set[str] = set()
            for artifact in valid_artifacts:
                path = resolve_task_path(root, artifact.relative_path)
                cited_domains.update(
                    _artifact_source_domains(path, source_domains)
                )
            required_cited_domains = min(2, minimum_domains)
            if len(cited_domains) < required_cited_domains:
                result.producer_issues.append(
                    f"交付文件至少需要写入 {required_cited_domains} 个来源 URL，"
                    f"当前只能识别 {len(cited_domains)} 个来源域名"
                )

    reviewer = next((node for node in nodes if node.role == "reviewer"), None)
    if reviewer is None:
        result.reviewer_issues.append("执行计划缺少 Reviewer")
        return result

    successful_calls = list(
        db.scalars(
            select(ToolCall).where(
                ToolCall.node_id == reviewer.id,
                ToolCall.status == ToolCallStatus.SUCCEEDED,
                ToolCall.tool_name.in_(["inspect_document", "read_text"]),
            )
        )
    )
    inspected = {
        _normalized_tool_path((call.arguments or {}).get("path"))
        for call in successful_calls
    }
    inspected.discard("")

    required_inspections = [
        artifact
        for artifact in valid_artifacts
        if Path(artifact.filename).suffix.lower() in INSPECTABLE_SUFFIXES
    ]
    missing: list[str] = []
    for artifact in required_inspections:
        relative = _normalized_tool_path(artifact.relative_path)
        if relative in inspected:
            result.verified_paths.add(relative)
        else:
            missing.append(artifact.filename)
    if missing:
        preview = "、".join(missing[:8])
        suffix = f" 等 {len(missing)} 个文件" if len(missing) > 8 else ""
        result.reviewer_issues.append(
            f"Reviewer 尚未逐一检查：{preview}{suffix}"
        )
    return result


def mark_verified_artifacts(db: Session, task_id: str, paths: set[str]) -> None:
    if not paths:
        return
    for artifact in db.scalars(
        select(Artifact).where(Artifact.task_id == task_id, Artifact.is_final.is_(True))
    ):
        if _normalized_tool_path(artifact.relative_path) in paths:
            artifact.inspection_status = "VERIFIED"
