from datetime import UTC, datetime

from app.agent.deepseek import ChatResult, ModelUsage
from app.db import SessionLocal
from app.memory import MemoryAnalysis, merge_analysis, memory_context
from app.models import MemoryExtraction, Task, UserMemory


def test_archive_creates_queryable_memory_job(authenticated_client):
    task = authenticated_client.post(
        "/api/tasks",
        json={"prompt": "以后所有报告都使用中文", "start_immediately": False},
    ).json()
    archived = authenticated_client.post(f"/api/tasks/{task['id']}/archive")
    assert archived.status_code == 202
    assert archived.json()["memory_status"] == "QUEUED"
    result = authenticated_client.get("/api/tasks/archived").json()
    assert result["total"] == 1
    assert result["items"][0]["id"] == task["id"]
    assert result["items"][0]["memory_status"] == "QUEUED"


def test_archive_restore_keeps_job(authenticated_client):
    task = authenticated_client.post(
        "/api/tasks",
        json={"prompt": "归档后恢复", "start_immediately": False},
    ).json()
    authenticated_client.post(f"/api/tasks/{task['id']}/archive")
    restored = authenticated_client.post(f"/api/tasks/{task['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["deleted_at"] is None
    assert authenticated_client.get("/api/tasks/archived").json()["total"] == 0


def test_explicit_memory_activates_and_is_injected(authenticated_client):
    task = authenticated_client.post(
        "/api/tasks",
        json={"prompt": "以后默认使用中文", "start_immediately": False},
    ).json()
    authenticated_client.post(f"/api/tasks/{task['id']}/archive")
    with SessionLocal() as db:
        extraction = db.query(MemoryExtraction).filter_by(task_id=task["id"]).one()
        analysis = MemoryAnalysis.model_validate(
            {
                "task_summary": "用户设置输出语言",
                "habit_summary_delta": "偏好中文",
                "reusable_memories": [
                    {
                        "category": "preference",
                        "key": "output.language",
                        "statement": "默认使用中文回答",
                        "confidence": 0.98,
                        "explicit": True,
                        "evidence_refs": ["message:1"],
                        "value": {"language": "zh-CN"},
                    }
                ],
            }
        )
        merge_analysis(db, extraction, analysis)
        db.commit()
        memory = db.query(UserMemory).filter_by(user_id=extraction.user_id).one()
        assert memory.status == "ACTIVE"
        assert "默认使用中文回答" in memory_context(db, extraction.user_id)
    memories = authenticated_client.get("/api/memories").json()
    assert memories["total"] == 1
    assert memories["items"][0]["status"] == "ACTIVE"


def test_inferred_memory_requires_two_archives(authenticated_client):
    task = authenticated_client.post(
        "/api/tasks",
        json={"prompt": "生成一个月报", "start_immediately": False},
    ).json()
    authenticated_client.post(f"/api/tasks/{task['id']}/archive")
    with SessionLocal() as db:
        extraction = db.query(MemoryExtraction).filter_by(task_id=task["id"]).one()
        analysis = MemoryAnalysis.model_validate(
            {
                "task_summary": "制作月报",
                "reusable_memories": [
                    {
                        "category": "habit",
                        "key": "report.monthly",
                        "statement": "经常制作月报",
                        "confidence": 0.7,
                        "explicit": False,
                    }
                ],
            }
        )
        merge_analysis(db, extraction, analysis)
        db.commit()
        memory = db.query(UserMemory).filter_by(memory_key="report.monthly").one()
        assert memory.status == "CANDIDATE"
        merge_analysis(db, extraction, analysis)
        db.commit()
        assert memory.status == "ACTIVE"


def test_memory_can_be_disabled(authenticated_client):
    task = authenticated_client.post(
        "/api/tasks",
        json={"prompt": "记住输出为 Markdown", "start_immediately": False},
    ).json()
    authenticated_client.post(f"/api/tasks/{task['id']}/archive")
    with SessionLocal() as db:
        extraction = db.query(MemoryExtraction).filter_by(task_id=task["id"]).one()
        memory = UserMemory(
            user_id=extraction.user_id,
            category="format",
            memory_key="output.markdown",
            statement="默认输出 Markdown",
            confidence=0.9,
            status="ACTIVE",
            source_task_id=task["id"],
        )
        db.add(memory)
        db.commit()
        memory_id = memory.id
    response = authenticated_client.post(f"/api/memories/{memory_id}/disable")
    assert response.status_code == 200
    assert response.json()["status"] == "DISABLED"
