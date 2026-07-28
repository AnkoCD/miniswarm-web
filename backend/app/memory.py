import json
import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.deepseek import ChatResult, DeepSeekClient, DeepSeekError
from app.core.config import Settings, get_settings
from app.models import (
    Artifact,
    MemoryExtraction,
    MemoryRevision,
    ProjectMemory,
    ProjectMemoryProfile,
    Task,
    TaskMessage,
    TaskNode,
    UserMemory,
    UserMemoryProfile,
)


SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_ -]?key|password|密码|token|secret)\s*[:=]\s*\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
)


def redact_secrets(text: str) -> str:
    result = text
    for pattern in SECRET_PATTERNS:
        result = pattern.sub("[敏感信息已移除]", result)
    return result


class ExtractedMemory(BaseModel):
    category: Literal[
        "preference", "habit", "constraint", "workflow", "format", "correction", "project"
    ]
    key: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,119}$")
    statement: str = Field(min_length=2, max_length=2000)
    confidence: float = Field(ge=0, le=1)
    explicit: bool = False
    evidence_refs: list[str] = Field(default_factory=list, max_length=8)
    value: dict = Field(default_factory=dict)


class MemoryAnalysis(BaseModel):
    task_summary: str = Field(min_length=2, max_length=2000)
    habit_summary_delta: str = Field(default="", max_length=2000)
    reusable_memories: list[ExtractedMemory] = Field(default_factory=list, max_length=10)


MEMORY_SYSTEM_PROMPT = """你是 MiniSwarm 的归档记忆整理器。只输出 JSON 对象，不输出 Markdown。
目标是提取该用户以后仍然有用的长期偏好、习惯、约束、工作流、格式要求、纠错经验和项目约定。
不要保存 API Key、密码、Token、Secret、联系方式、支付信息、模型内部思考或一次性任务细节。
explicit 只有在用户明确说出长期要求时才为 true；从行为推断的习惯必须为 false。
key 使用稳定的英文小写标识，相同含义应使用相同 key。
输出结构：
{"task_summary":"归档任务摘要","habit_summary_delta":"本任务反映的使用习惯",
"reusable_memories":[{"category":"preference","key":"output.language","statement":"默认使用中文回答",
"confidence":0.95,"explicit":true,"evidence_refs":["message:1"],"value":{}}]}
"""


def build_archive_digest(db: Session, task: Task) -> str:
    messages = list(
        db.scalars(
            select(TaskMessage)
            .where(TaskMessage.task_id == task.id)
            .order_by(TaskMessage.created_at.desc())
            .limit(80)
        )
    )
    messages.reverse()
    nodes = list(
        db.scalars(
            select(TaskNode)
            .where(TaskNode.task_id == task.id, TaskNode.revision == task.current_revision)
            .order_by(TaskNode.created_at)
        )
    )
    artifacts = list(
        db.scalars(select(Artifact).where(Artifact.task_id == task.id).order_by(Artifact.created_at))
    )
    lines = [
        f"task:{task.id}",
        f"title:{task.title}",
        f"type:{task.task_type}",
        f"model:{task.model_mode}",
        f"execution:{task.execution_mode}",
        f"autonomy:{task.autonomy_mode}",
        "messages:",
    ]
    for index, item in enumerate(messages, 1):
        lines.append(f"message:{index} [{item.role}/{item.mode}] {item.content}")
    lines.append("final_nodes:")
    for node in nodes:
        if node.result_summary:
            lines.append(f"node:{node.node_key} [{node.role}] {node.result_summary}")
    lines.append("artifacts:")
    for artifact in artifacts:
        lines.append(f"- {artifact.filename} ({artifact.mime_type}, {artifact.size} bytes)")
    return redact_secrets("\n".join(lines))[-60_000:]


def analyze_archive(
    db: Session,
    task: Task,
    *,
    client: DeepSeekClient | None = None,
    settings: Settings | None = None,
) -> tuple[MemoryAnalysis, ChatResult]:
    settings = settings or get_settings()
    result = (client or DeepSeekClient(settings)).chat(
        model=settings.model_memory,
        messages=[
            {"role": "system", "content": MEMORY_SYSTEM_PROMPT},
            {"role": "user", "content": build_archive_digest(db, task)},
        ],
        thinking=True,
        response_format={"type": "json_object"},
        max_tokens=4_000,
    )
    content = result.message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise DeepSeekError("归档记忆分析返回了空内容")
    try:
        return MemoryAnalysis.model_validate(json.loads(content)), result
    except (json.JSONDecodeError, ValueError) as exc:
        raise DeepSeekError("归档记忆分析结果不符合约定") from exc


def _snapshot(memory: UserMemory) -> dict:
    return {
        "category": memory.category,
        "memory_key": memory.memory_key,
        "statement": memory.statement,
        "confidence": memory.confidence,
        "status": memory.status,
        "occurrence_count": memory.occurrence_count,
    }


def merge_analysis(
    db: Session,
    extraction: MemoryExtraction,
    analysis: MemoryAnalysis,
) -> int:
    now = datetime.now(UTC)
    changed = 0
    settings = get_settings()
    current_count = db.scalar(
        select(func.count()).select_from(UserMemory).where(
            UserMemory.user_id == extraction.user_id,
            UserMemory.status.in_(["ACTIVE", "CANDIDATE"]),
        )
    ) or 0
    for item in analysis.reusable_memories:
        statement = redact_secrets(item.statement).strip()
        if not statement or "[敏感信息已移除]" in statement:
            continue
        memory = db.scalar(
            select(UserMemory).where(
                UserMemory.user_id == extraction.user_id,
                UserMemory.category == item.category,
                UserMemory.memory_key == item.key,
            )
        )
        if memory is None:
            if current_count >= settings.max_memories_per_user:
                continue
            status = "ACTIVE" if item.explicit and item.confidence >= 0.8 else "CANDIDATE"
            memory = UserMemory(
                user_id=extraction.user_id,
                category=item.category,
                memory_key=item.key,
                statement=statement,
                value_json=item.value,
                confidence=item.confidence,
                status=status,
                source_task_id=extraction.task_id,
                evidence_refs=item.evidence_refs,
            )
            db.add(memory)
            db.flush()
            current_count += 1
            before = {}
            action = "CREATED"
        else:
            before = _snapshot(memory)
            memory.occurrence_count += 1
            memory.last_seen_at = now
            memory.updated_at = now
            memory.source_task_id = extraction.task_id
            memory.evidence_refs = list(dict.fromkeys(memory.evidence_refs + item.evidence_refs))[-20:]
            if item.explicit or item.confidence >= memory.confidence:
                memory.statement = statement
                memory.value_json = item.value
            memory.confidence = max(memory.confidence, item.confidence)
            if memory.status in {"CANDIDATE", "SUPERSEDED"} and (
                item.explicit and item.confidence >= 0.8 or memory.occurrence_count >= 2
            ):
                memory.status = "ACTIVE"
            action = "MERGED"
        db.add(
            MemoryRevision(
                memory_id=memory.id,
                user_id=extraction.user_id,
                source_task_id=extraction.task_id,
                action=action,
                before_json=before,
                after_json=_snapshot(memory),
            )
        )
        changed += 1
    extraction.task_summary = analysis.task_summary
    extraction.habit_summary_delta = analysis.habit_summary_delta
    extraction.memory_items_count = changed
    rebuild_profile(db, extraction.user_id)
    return changed


def merge_project_analysis(
    db: Session,
    task: Task,
    analysis: MemoryAnalysis,
) -> int:
    if not task.project_id:
        return 0
    now = datetime.now(UTC)
    changed = 0
    for item in analysis.reusable_memories:
        if item.category not in {"project", "constraint", "workflow", "format", "correction"}:
            continue
        statement = redact_secrets(item.statement).strip()
        if not statement or "[敏感信息已移除]" in statement:
            continue
        existing = db.scalar(
            select(ProjectMemory).where(
                ProjectMemory.project_id == task.project_id,
                ProjectMemory.statement == statement,
            )
        )
        if existing is not None:
            existing.updated_at = now
            existing.source_task_id = task.id
            existing.evidence_refs = list(
                dict.fromkeys((existing.evidence_refs or []) + item.evidence_refs)
            )[-20:]
            continue
        db.add(
            ProjectMemory(
                project_id=task.project_id,
                category=item.category,
                statement=statement,
                status="ACTIVE" if item.explicit and item.confidence >= 0.8 else "CANDIDATE",
                source_task_id=task.id,
                evidence_refs=item.evidence_refs,
            )
        )
        changed += 1
    db.flush()
    active = list(
        db.scalars(
            select(ProjectMemory)
            .where(
                ProjectMemory.project_id == task.project_id,
                ProjectMemory.status == "ACTIVE",
            )
            .order_by(ProjectMemory.updated_at.desc())
            .limit(50)
        )
    )
    summary = "\n".join(f"- {item.statement}" for item in active) or "尚未形成已确认的项目记忆。"
    profile = db.get(ProjectMemoryProfile, task.project_id)
    if profile is None:
        profile = ProjectMemoryProfile(project_id=task.project_id, summary=summary[:6000])
        db.add(profile)
    else:
        profile.summary = summary[:6000]
        profile.version += 1
        profile.updated_at = now
    return changed


def rebuild_profile(db: Session, user_id: str) -> UserMemoryProfile:
    memories = list(
        db.scalars(
            select(UserMemory)
            .where(UserMemory.user_id == user_id, UserMemory.status == "ACTIVE")
            .order_by(
                UserMemory.category,
                UserMemory.occurrence_count.desc(),
                UserMemory.confidence.desc(),
            )
            .limit(80)
        )
    )
    grouped: dict[str, list[str]] = {}
    for memory in memories:
        grouped.setdefault(memory.category, []).append(memory.statement)
    labels = {
        "preference": "明确偏好",
        "habit": "使用习惯",
        "constraint": "长期约束",
        "workflow": "工作流程",
        "format": "输出格式",
        "correction": "纠错经验",
        "project": "项目背景",
    }
    summary = "\n".join(
        f"{labels.get(category, category)}：{'；'.join(items[:12])}"
        for category, items in grouped.items()
    ) or "尚未形成已确认的全局记忆。"
    profile = db.get(UserMemoryProfile, user_id)
    now = datetime.now(UTC)
    if profile is None:
        profile = UserMemoryProfile(
            user_id=user_id,
            summary=summary[:6_000],
            defaults_json={},
            version=1,
            updated_at=now,
        )
        db.add(profile)
    else:
        profile.summary = summary[:6_000]
        profile.version += 1
        profile.updated_at = now
    db.flush()
    return profile


def memory_context(db: Session, user_id: str) -> str:
    settings = get_settings()
    profile = db.get(UserMemoryProfile, user_id)
    memories = list(
        db.scalars(
            select(UserMemory)
            .where(UserMemory.user_id == user_id, UserMemory.status == "ACTIVE")
            .order_by(
                UserMemory.occurrence_count.desc(),
                UserMemory.confidence.desc(),
                UserMemory.last_seen_at.desc(),
            )
            .limit(12)
        )
    )
    if not profile and not memories:
        return ""
    lines = [profile.summary[:3_000] if profile else ""]
    lines.extend(f"- [{item.category}] {item.statement}" for item in memories)
    return "\n".join(filter(None, lines))[: settings.max_memory_context_chars]


def memory_count(db: Session, user_id: str) -> int:
    return db.scalar(
        select(func.count()).select_from(UserMemory).where(
            UserMemory.user_id == user_id,
            UserMemory.status.in_(["ACTIVE", "CANDIDATE"]),
        )
    ) or 0
