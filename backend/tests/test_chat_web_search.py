from sqlalchemy import select

from app.agent.runner_client import RunnerResult
from app.core.config import get_settings
from app.db import SessionLocal
from app.models import Task, TaskSource, ToolCall, ToolCallStatus
from app.worker.tasks import _chat_web_context


def test_chat_web_context_records_tool_and_sources(authenticated_client, monkeypatch):
    task_data = authenticated_client.post(
        "/api/tasks",
        json={
            "prompt": "建立联网聊天",
            "execution_kind": "chat",
            "start_immediately": False,
        },
    ).json()
    monkeypatch.setattr(
        "app.worker.tasks.RunnerClient.execute",
        lambda self, **kwargs: RunnerResult(
            ok=True,
            summary="找到 1 条结果",
            data={
                "items": [
                    {
                        "title": "官方公告",
                        "url": "https://example.com/announcement",
                        "summary": "最新公告摘要",
                    }
                ]
            },
        ),
    )
    monkeypatch.setattr("app.worker.tasks.publish_task_event", lambda *args, **kwargs: True)

    with SessionLocal() as db:
        task = db.get(Task, task_data["id"])
        assert task is not None
        context = _chat_web_context(db, task, "今天的官方公告", get_settings())
        call = db.scalar(select(ToolCall).where(ToolCall.task_id == task.id))
        source = db.scalar(select(TaskSource).where(TaskSource.task_id == task.id))

    assert "联网检索结果" in context
    assert call is not None and call.status == ToolCallStatus.SUCCEEDED
    assert source is not None and source.url == "https://example.com/announcement"
