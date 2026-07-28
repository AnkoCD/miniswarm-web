import html
import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx


class WebToolError(RuntimeError):
    pass


NEWS_FEEDS = (
    (
        "Bing News",
        "https://www.bing.com/news/search",
        {"format": "rss", "mkt": "zh-CN"},
    ),
    (
        "中国新闻网",
        "https://www.chinanews.com.cn/rss/scroll-news.xml",
        {},
    ),
)


def _plain_text(value: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(html.unescape(text).split())


def _parse_rss(content: bytes, limit: int) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise WebToolError("新闻检索响应格式无效") from exc
    items: list[dict[str, str]] = []
    for item in root.findall("./channel/item")[:limit]:
        title = _plain_text(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        if not title or not link.startswith(("https://", "http://")):
            continue
        items.append(
            {
                "title": title,
                "summary": _plain_text(item.findtext("description"))[:1000],
                "published_at": (item.findtext("pubDate") or "").strip(),
                "url": link,
            }
        )
    return items


def search_news(
    query: str,
    limit: int = 10,
    *,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    query = query.strip()
    if not query or len(query) > 200:
        raise WebToolError("新闻检索词长度无效")
    limit = max(1, min(int(limit), 20))
    errors: list[str] = []
    with httpx.Client(
        timeout=20,
        follow_redirects=False,
        transport=transport,
        headers={"User-Agent": "MiniSwarm/0.1 (+news-rss)"},
    ) as client:
        for provider, endpoint, base_params in NEWS_FEEDS:
            params = dict(base_params)
            if provider == "Bing News":
                params["q"] = query
            try:
                response = client.get(endpoint, params=params)
                response.raise_for_status()
                if len(response.content) > 2 * 1024 * 1024:
                    raise WebToolError("新闻检索响应过大")
                items = _parse_rss(response.content, limit)
                if items:
                    return {
                        "query": query,
                        "provider": provider,
                        "count": len(items),
                        "items": items,
                    }
                errors.append(f"{provider}: 没有结果")
            except (httpx.HTTPError, WebToolError) as exc:
                errors.append(f"{provider}: {type(exc).__name__}")
    raise WebToolError(f"新闻检索服务暂时不可用（已尝试 {len(errors)} 个固定可信来源）")
