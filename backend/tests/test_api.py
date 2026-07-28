def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_authentication_required(client):
    assert client.get("/api/tasks").status_code == 401


def test_login_and_me(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "very-secure-test-password"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert "miniswarm_access_token" in response.cookies
    assert "access_token" not in response.cookies
    me = client.get("/api/auth/me")
    assert me.json()["username"] == "admin"
    assert "miniswarm_access_token=" in me.headers["set-cookie"]


def test_create_task_and_replay_events(authenticated_client):
    created = authenticated_client.post(
        "/api/tasks",
        json={
            "prompt": "生成一份测试报告",
            "task_type": "document",
            "model_mode": "deepseek-v4-pro",
            "execution_mode": "deep",
            "autonomy_mode": "yolo",
        },
    )
    assert created.status_code == 201
    task = created.json()
    assert task["status"] == "QUEUED"
    assert task["model_mode"] == "deepseek-v4-pro"
    assert task["execution_mode"] == "deep"
    assert task["autonomy_mode"] == "yolo"
    assert task["skill_mode"] == "auto"
    assert task["selected_skills"] == []
    events = authenticated_client.get(f"/api/tasks/{task['id']}/events").json()
    assert [item["type"] if "type" in item else item["event_type"] for item in events["items"]] == [
        "task.created",
        "task.queued",
    ]


def test_create_task_accepts_one_character_prompt(authenticated_client):
    created = authenticated_client.post(
        "/api/tasks",
        json={
            "prompt": "好",
            "execution_kind": "chat",
            "start_immediately": False,
        },
    )
    assert created.status_code == 201
    assert created.json()["prompt"] == "好"


def test_unknown_skill_and_empty_manual_selection_are_rejected(authenticated_client):
    unknown = authenticated_client.post(
        "/api/tasks",
        json={
            "prompt": "使用不存在的技能",
            "skill_mode": "manual",
            "selected_skills": ["not-installed"],
        },
    )
    assert unknown.status_code == 422
    empty = authenticated_client.post(
        "/api/tasks",
        json={"prompt": "手动选择技能", "skill_mode": "manual"},
    )
    assert empty.status_code == 422


def test_one_active_task_per_user(authenticated_client):
    first = authenticated_client.post("/api/tasks", json={"prompt": "第一个有效任务"})
    assert first.status_code == 201
    second = authenticated_client.post("/api/tasks", json={"prompt": "第二个有效任务"})
    assert second.status_code == 409


def test_admin_can_create_only_three_accounts(authenticated_client):
    for username in ("member1", "member2"):
        response = authenticated_client.post(
            "/api/admin/users",
            json={"username": username, "password": "safe-member-password", "role": "user"},
        )
        assert response.status_code == 201
    rejected = authenticated_client.post(
        "/api/admin/users",
        json={"username": "member3", "password": "safe-member-password", "role": "user"},
    )
    assert rejected.status_code == 409


def test_approval_is_single_decision(authenticated_client):
    from app.db import SessionLocal
    from app.models import Approval, Task, ToolCall
    from app.services import request_approval

    created = authenticated_client.post("/api/tasks", json={"prompt": "需要删除一个文件"}).json()
    with SessionLocal() as db:
        task = db.get(Task, created["id"])
        call = ToolCall(task_id=task.id, tool_name="move_to_trash", arguments={"path": "workspace/a.txt"})
        db.add(call)
        db.flush()
        approval = request_approval(
            db, task, call, operation="move_to_trash", summary="把 a.txt 移入回收站",
            arguments={"path": "workspace/a.txt"},
        )
        approval_id = approval.id
        db.commit()
    first = authenticated_client.post(
        f"/api/tasks/{created['id']}/approvals/{approval_id}", json={"decision": "allow_once"}
    )
    assert first.status_code == 200
    assert first.json()["status"] == "APPROVED_ONCE"
    second = authenticated_client.post(
        f"/api/tasks/{created['id']}/approvals/{approval_id}", json={"decision": "deny"}
    )
    assert second.status_code == 409


def test_draft_upload_then_start(authenticated_client, monkeypatch):
    queued: list[str] = []
    monkeypatch.setattr(
        "app.api.tasks.run_task.apply_async",
        lambda args, queue: queued.append(args[0]),
    )
    created = authenticated_client.post(
        "/api/tasks", json={"prompt": "分析上传文件", "start_immediately": False}
    )
    assert created.status_code == 201
    task = created.json()
    assert task["status"] == "CREATED"
    uploaded = authenticated_client.post(
        f"/api/tasks/{task['id']}/files",
        files={"upload": ("sample.txt", b"hello", "text/plain")},
    )
    assert uploaded.status_code == 201
    artifact = uploaded.json()
    preview = authenticated_client.get(
        f"/api/tasks/{task['id']}/artifacts/{artifact['id']}/preview"
    )
    assert preview.text == "hello"
    started = authenticated_client.post(f"/api/tasks/{task['id']}/start")
    assert started.status_code == 200
    assert queued == [task["id"]]


def test_html_artifact_uses_sandbox_preview_kind(authenticated_client):
    task = authenticated_client.post(
        "/api/tasks", json={"prompt": "预览网页", "start_immediately": False}
    ).json()
    uploaded = authenticated_client.post(
        f"/api/tasks/{task['id']}/files",
        files={
            "upload": (
                "report.html",
                b"<!doctype html><html><body><h1>Preview</h1><script>alert(1)</script></body></html>",
                "text/html",
            )
        },
    )
    assert uploaded.status_code == 201
    artifact = uploaded.json()

    metadata = authenticated_client.get(
        f"/api/tasks/{task['id']}/artifacts/{artifact['id']}/preview-metadata"
    )
    assert metadata.status_code == 200
    assert metadata.json()["kind"] == "html"

    inline = authenticated_client.get(
        f"/api/tasks/{task['id']}/artifacts/{artifact['id']}/inline"
    )
    assert inline.status_code == 200
    assert inline.headers["content-type"].startswith("text/plain")
    assert "<script>alert(1)</script>" in inline.text


def test_upload_never_overwrites(authenticated_client):
    task = authenticated_client.post(
        "/api/tasks", json={"prompt": "处理文件", "start_immediately": False}
    ).json()
    url = f"/api/tasks/{task['id']}/files"
    assert authenticated_client.post(url, files={"upload": ("same.txt", b"one", "text/plain")}).status_code == 201
    assert authenticated_client.post(url, files={"upload": ("same.txt", b"two", "text/plain")}).status_code == 409


def test_delete_soft_archives_task(authenticated_client):
    from app.db import SessionLocal
    from app.models import Task

    task = authenticated_client.post("/api/tasks", json={"prompt": "稍后归档的任务"}).json()
    response = authenticated_client.delete(f"/api/tasks/{task['id']}")
    assert response.status_code == 204
    assert authenticated_client.get(f"/api/tasks/{task['id']}").status_code == 404
    with SessionLocal() as db:
        stored = db.get(Task, task["id"])
        assert stored is not None
        assert stored.deleted_at is not None


def test_admin_worker_status(authenticated_client, monkeypatch):
    class Inspector:
        def ping(self):
            return {"worker-agent@host": {"ok": "pong"}}

        def active(self):
            return {"worker-agent@host": [{"id": "one"}]}

        def reserved(self):
            return {"worker-agent@host": []}

    monkeypatch.setattr("app.api.admin.celery_app.control.inspect", lambda timeout: Inspector())
    response = authenticated_client.get("/api/admin/workers")
    assert response.status_code == 200
    assert response.json()[0]["active_tasks"] == 1


def test_task_chat_is_persisted(authenticated_client, monkeypatch):
    queued: list[str] = []
    monkeypatch.setattr(
        "app.api.tasks.chat_reply_task.apply_async",
        lambda args, queue: queued.append(args[0]),
    )
    task = authenticated_client.post(
        "/api/tasks",
        json={"prompt": "创建报告", "start_immediately": False},
    ).json()
    response = authenticated_client.post(
        f"/api/tasks/{task['id']}/messages",
        json={"content": "标题应该怎么改？", "mode": "chat"},
    )
    assert response.status_code == 202
    messages = authenticated_client.get(f"/api/tasks/{task['id']}/messages").json()
    assert [item["content"] for item in messages] == ["创建报告", "标题应该怎么改？"]
    assert queued == [task["id"]]


def test_file_revision_starts_new_revision(authenticated_client, monkeypatch):
    from app.db import SessionLocal
    from app.models import Task, TaskStatus

    queued: list[str] = []
    monkeypatch.setattr(
        "app.api.tasks.run_task.apply_async",
        lambda args, queue: queued.append(args[0]),
    )
    task = authenticated_client.post(
        "/api/tasks",
        json={"prompt": "创建报告", "start_immediately": False},
    ).json()
    with SessionLocal() as db:
        stored = db.get(Task, task["id"])
        stored.status = TaskStatus.FAILED
        db.commit()
    response = authenticated_client.post(
        f"/api/tasks/{task['id']}/messages",
        json={"content": "把标题改成月报", "mode": "revise"},
    )
    assert response.status_code == 202
    refreshed = authenticated_client.get(f"/api/tasks/{task['id']}").json()
    assert refreshed["status"] == "QUEUED"
    assert refreshed["current_revision"] == 1
    assert queued == [task["id"]]
