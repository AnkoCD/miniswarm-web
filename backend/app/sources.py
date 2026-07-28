from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import Task, TaskSource


URL_PATTERN = re.compile(
    r"https?://[^\s<>\]\[()\"'`，。；：！？、]+",
    re.IGNORECASE,
)
MARKDOWN_LINK_PATTERN = re.compile(
    r"\[([^\]\r\n]{1,500})\]\((https?://[^)\s]+)\)",
    re.IGNORECASE,
)
ANYSEARCH_RESULT_PATTERN = re.compile(
    r"^###\s+\d+\.\s+([^\r\n]{1,500}?)\s*$"
    r".{0,300}?^-\s+\*\*URL\*\*:\s*(https?://\S+)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
SENSITIVE_QUERY_KEYS = {
    "api_key",
    "apikey",
    "key",
    "token",
    "access_token",
    "auth",
    "authorization",
    "signature",
    "sig",
    "secret",
    "password",
}


def _iter_source_items(value: object):
    if isinstance(value, list):
        for item in value:
            yield from _iter_source_items(item)
        return
    if not isinstance(value, dict):
        return
    if value.get("url") or value.get("link"):
        yield value
    for key, child in value.items():
        if key in {"url", "link", "content", "text", "snippet", "summary"}:
            continue
        if isinstance(child, (list, dict)):
            yield from _iter_source_items(child)


def _iter_text_source_items(value: object):
    if isinstance(value, list):
        for item in value:
            yield from _iter_text_source_items(item)
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"content", "text", "summary", "snippet"} and isinstance(child, str):
                seen: set[str] = set()
                primary_results = list(ANYSEARCH_RESULT_PATTERN.findall(child))
                if primary_results:
                    for title, url in primary_results:
                        position = child.find(url)
                        yield {
                            "title": title.strip().strip("[]: "),
                            "url": url,
                            "summary": child[position:position + 700],
                        }
                    continue
                for title, url in MARKDOWN_LINK_PATTERN.findall(child):
                    seen.add(url)
                    yield {
                        "title": title.strip(),
                        "url": url,
                        "summary": child[max(0, child.find(url) - 180):child.find(url) + 500],
                    }
                for url in URL_PATTERN.findall(child):
                    if url in seen:
                        continue
                    position = child.find(url)
                    yield {
                        "url": url,
                        "summary": child[max(0, position - 180):position + 500],
                    }
            elif isinstance(child, (list, dict)):
                yield from _iter_text_source_items(child)


def _published_at(item: dict) -> datetime | None:
    raw = item.get("published_at") or item.get("published") or item.get("date")
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def sanitize_url(value: str) -> tuple[str, str, str] | None:
    value = re.split(r"[`，。；：！？、]", value, maxsplit=1)[0]
    try:
        parts = urlsplit(value.rstrip(".,;:!?，。；：！？、`"))
    except ValueError:
        return None
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        return None
    safe_query = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in SENSITIVE_QUERY_KEYS
    ]
    host = parts.hostname.lower()
    try:
        port_number = parts.port
    except ValueError:
        return None
    port = f":{port_number}" if port_number and port_number not in {80, 443} else ""
    netloc = f"{host}{port}"
    normalized_path = parts.path or "/"
    normalized = urlunsplit(
        (parts.scheme.lower(), netloc, normalized_path, urlencode(sorted(safe_query)), "")
    )
    return normalized, normalized, host


def capture_user_urls(db: Session, task: Task, content: str) -> int:
    created = 0
    for raw in URL_PATTERN.findall(content):
        sanitized = sanitize_url(raw)
        if sanitized is None:
            continue
        url, normalized, domain = sanitized
        existing = db.scalar(
            select(TaskSource.id).where(
                TaskSource.task_id == task.id,
                TaskSource.normalized_url == normalized,
            )
        )
        if existing is not None:
            continue
        db.add(
            TaskSource(
                task_id=task.id,
                title=domain,
                url=url,
                normalized_url=normalized,
                domain=domain,
                summary="用户在消息中提供的链接；系统尚未自动访问。",
                source_type="user_url",
                source_agent="user",
            )
        )
        created += 1
    return created


def capture_search_results(
    db: Session,
    task: Task,
    *,
    node_id: str | None,
    source_type: str,
    source_agent: str,
    data: dict,
    parse_text_urls: bool = False,
) -> int:
    created = 0
    items = list(_iter_source_items(data))
    if parse_text_urls:
        items.extend(_iter_text_source_items(data))
    unique_items: dict[str, tuple[dict, tuple[str, str, str]]] = {}
    for item in items:
        raw_url = str(item.get("url") or item.get("link") or "")
        sanitized = sanitize_url(raw_url)
        if sanitized is None:
            continue
        url, normalized, domain = sanitized
        unique_items.setdefault(normalized, (item, (url, normalized, domain)))

    dialect = db.get_bind().dialect.name
    for item, (url, normalized, domain) in list(unique_items.values())[:50]:
        existing = db.scalar(
            select(TaskSource).where(
                TaskSource.task_id == task.id,
                TaskSource.normalized_url == normalized,
            )
        )
        if existing is not None:
            if not existing.summary:
                existing.summary = str(
                    item.get("summary")
                    or item.get("snippet")
                    or item.get("content")
                    or ""
                )[:4000]
            if existing.title == existing.domain:
                existing.title = str(item.get("title") or domain)[:500]
            existing.published_at = existing.published_at or _published_at(item)
            existing.fetched_at = datetime.now(UTC)
            continue
        now = datetime.now(UTC)
        values = {
            "id": str(uuid.uuid4()),
            "task_id": task.id,
            "node_id": node_id,
            "title": str(item.get("title") or domain)[:500],
            "url": url,
            "normalized_url": normalized,
            "domain": domain,
            "summary": str(
                item.get("summary")
                or item.get("snippet")
                or item.get("content")
                or ""
            )[:4000],
            "source_type": source_type,
            "source_agent": source_agent,
            "published_at": _published_at(item),
            "fetched_at": now,
            "created_at": now,
        }
        if dialect == "postgresql":
            statement = postgresql_insert(TaskSource).values(**values)
            statement = statement.on_conflict_do_nothing(
                index_elements=["task_id", "normalized_url"]
            )
        elif dialect == "sqlite":
            statement = sqlite_insert(TaskSource).values(**values)
            statement = statement.on_conflict_do_nothing(
                index_elements=["task_id", "normalized_url"]
            )
        else:
            db.add(TaskSource(**values))
            created += 1
            continue
        result = db.execute(statement)
        if result.rowcount:
            created += 1
    return created
