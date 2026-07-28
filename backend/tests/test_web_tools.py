import httpx

from app.agent.risk import approval_reason
from app.agent.web_tools import search_news


RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss><channel><item>
  <title>Test &amp; News</title>
  <link>https://example.com/news/1</link>
  <description><![CDATA[<b>Summary</b> text]]></description>
  <pubDate>Wed, 22 Jul 2026 10:00:00 GMT</pubDate>
</item></channel></rss>"""


def test_search_news_parses_fixed_rss_endpoint():
    def handler(request: httpx.Request):
        assert request.url.host == "www.bing.com"
        return httpx.Response(200, content=RSS)

    result = search_news("today", transport=httpx.MockTransport(handler))
    assert result["count"] == 1
    assert result["provider"] == "Bing News"
    assert result["items"][0]["title"] == "Test & News"
    assert result["items"][0]["summary"] == "Summary text"


def test_search_news_falls_back_to_chinanews():
    def handler(request: httpx.Request):
        if request.url.host == "www.bing.com":
            return httpx.Response(503, content=b"unavailable")
        assert request.url == "https://www.chinanews.com.cn/rss/scroll-news.xml"
        return httpx.Response(200, content=RSS)

    result = search_news("今日新闻", transport=httpx.MockTransport(handler))
    assert result["provider"] == "中国新闻网"
    assert result["count"] == 1


def test_search_news_always_requires_approval(tmp_path):
    reason = approval_reason("search_news", {"query": "today"}, tmp_path)
    assert reason and "外部网络" in reason
