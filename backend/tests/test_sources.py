from app.db import SessionLocal
from app.models import Task, TaskSource, User
from app.sources import capture_search_results
from app.sources import sanitize_url


def test_capture_search_results_finds_nested_anysearch_items():
    with SessionLocal() as db:
        user = db.query(User).filter_by(username="admin").one()
        task = Task(
            owner_id=user.id,
            title="调研",
            prompt="联网检索资料",
            task_type="document",
        )
        db.add(task)
        db.flush()
        created = capture_search_results(
            db,
            task,
            node_id=None,
            source_type="anysearch",
            source_agent="researcher",
            data={
                "results": [
                    {
                        "query": "topic",
                        "items": [
                            {
                                "title": "Primary",
                                "url": "https://example.com/report?token=secret&year=2026",
                                "snippet": "Evidence",
                                "published_at": "2026-07-28T00:00:00Z",
                            }
                        ],
                    }
                ]
            },
        )
        db.commit()
        assert created == 1
        source = db.query(TaskSource).filter_by(task_id=task.id).one()
        assert source.title == "Primary"
        assert source.normalized_url == "https://example.com/report?year=2026"
        assert source.published_at is not None


def test_capture_search_results_finds_urls_in_anysearch_text_payload():
    with SessionLocal() as db:
        user = db.query(User).filter_by(username="admin").one()
        task = Task(
            owner_id=user.id,
            title="文本结果调研",
            prompt="联网检索资料",
            task_type="document",
        )
        db.add(task)
        db.flush()
        created = capture_search_results(
            db,
            task,
            node_id=None,
            source_type="anysearch",
            source_agent="researcher",
            data={
                "content": (
                    "1. [Microsoft Open XML](https://learn.microsoft.com/office/open-xml/)\n"
                    "2. LibreOffice guide: https://help.libreoffice.org/latest/en-US/"
                )
            },
            parse_text_urls=True,
        )
        db.commit()
        sources = db.query(TaskSource).filter_by(task_id=task.id).all()
        assert created == 2
        assert {item.domain for item in sources} == {
            "learn.microsoft.com",
            "help.libreoffice.org",
        }


def test_sanitize_url_rejects_invalid_port_and_stops_at_backtick():
    assert sanitize_url("http://127.0.0.1:bad-port/path") is None
    parsed = sanitize_url("http://127.0.0.1:26315`打开。只在本机使用")
    assert parsed == (
        "http://127.0.0.1:26315/",
        "http://127.0.0.1:26315/",
        "127.0.0.1",
    )


def test_anysearch_text_capture_uses_primary_results_not_navigation_links():
    with SessionLocal() as db:
        user = db.query(User).filter_by(username="admin").one()
        task = Task(
            owner_id=user.id,
            title="主结果去重",
            prompt="深度调研",
            task_type="document",
        )
        db.add(task)
        db.flush()
        payload = {
            "content": (
                "## Search Results (2 results)\n\n"
                "### 1. [MS-DOCX]: Word Extensions\n"
                "- **URL**: https://learn.microsoft.com/openspecs/ms-docx\n"
                "- 正文导航：https://learn.microsoft.com/navigation/noise\n\n"
                "### 2. LibreOffice Writer Guide\n"
                "- **URL**: https://help.libreoffice.org/writer/guide\n"
                "- 站内链接：https://help.libreoffice.org/navigation/noise\n"
            )
        }
        first = capture_search_results(
            db,
            task,
            node_id=None,
            source_type="anysearch",
            source_agent="researcher",
            data=payload,
            parse_text_urls=True,
        )
        second = capture_search_results(
            db,
            task,
            node_id=None,
            source_type="anysearch",
            source_agent="researcher",
            data=payload,
            parse_text_urls=True,
        )
        db.commit()
        sources = db.query(TaskSource).filter_by(task_id=task.id).all()
        assert first == 2
        assert second == 0
        assert {item.normalized_url for item in sources} == {
            "https://learn.microsoft.com/openspecs/ms-docx",
            "https://help.libreoffice.org/writer/guide",
        }
