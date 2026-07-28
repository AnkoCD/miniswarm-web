from fastapi.testclient import TestClient

from app.main import app


PASSWORD = "very-secure-member-password"


def _login(client: TestClient, username: str, password: str = PASSWORD) -> None:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200


def _create_members(admin: TestClient) -> None:
    for username in ("editor", "viewer"):
        response = admin.post(
            "/api/admin/users",
            json={"username": username, "password": PASSWORD, "role": "user"},
        )
        assert response.status_code == 201


def test_private_project_permissions_and_admin_privacy(authenticated_client, monkeypatch):
    monkeypatch.setattr("app.api.tasks.run_task.apply_async", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.api.tasks.chat_reply_task.apply_async", lambda *args, **kwargs: None)
    _create_members(authenticated_client)
    with TestClient(app) as editor, TestClient(app) as viewer:
        _login(editor, "editor")
        _login(viewer, "viewer")
        project = editor.post("/api/projects", json={"name": "私有项目"}).json()
        added = editor.post(
            f"/api/projects/{project['id']}/members",
            json={"username": "viewer", "role": "VIEWER"},
        )
        assert added.status_code == 201
        task = editor.post(
            "/api/tasks",
            json={
                "prompt": "仅项目成员可见的任务",
                "project_id": project["id"],
                "start_immediately": False,
            },
        ).json()

        assert viewer.get(f"/api/tasks/{task['id']}").status_code == 200
        assert viewer.post(
            f"/api/tasks/{task['id']}/messages",
            json={"content": "我不应该能写入", "mode": "chat"},
        ).status_code == 403
        # 管理员没有被邀请，因此不能穿透私人项目。
        assert authenticated_client.get(f"/api/tasks/{task['id']}").status_code == 404
        assert authenticated_client.get(f"/api/projects/{project['id']}").status_code == 404


def test_message_idempotency_and_source_redaction(authenticated_client, monkeypatch):
    monkeypatch.setattr("app.api.tasks.chat_reply_task.apply_async", lambda *args, **kwargs: None)
    project = authenticated_client.post("/api/projects", json={"name": "资料项目"}).json()
    task = authenticated_client.post(
        "/api/tasks",
        json={
            "prompt": "先聊天",
            "project_id": project["id"],
            "execution_kind": "chat",
            "start_immediately": False,
            "client_request_id": "request-12345678",
        },
    ).json()
    payload = {
        "content": "参考 https://example.com/report?api_key=secret&lang=zh",
        "mode": "chat",
        "client_message_id": "message-12345678",
    }
    first = authenticated_client.post(f"/api/tasks/{task['id']}/messages", json=payload)
    second = authenticated_client.post(f"/api/tasks/{task['id']}/messages", json=payload)
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]

    sources = authenticated_client.get(f"/api/tasks/{task['id']}/sources").json()
    assert len(sources) == 1
    assert "api_key" not in sources[0]["url"]
    assert "secret" not in sources[0]["url"]
    assert "lang=zh" in sources[0]["url"]


def test_chat_does_not_consume_active_task_slot(authenticated_client, monkeypatch):
    monkeypatch.setattr("app.api.tasks.run_task.apply_async", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.api.tasks.chat_reply_task.apply_async", lambda *args, **kwargs: None)
    project = authenticated_client.post("/api/projects", json={"name": "并发项目"}).json()
    chat = authenticated_client.post(
        "/api/tasks",
        json={
            "prompt": "普通聊天",
            "project_id": project["id"],
            "execution_kind": "chat",
            "start_immediately": True,
        },
    )
    assert chat.status_code == 201
    task = authenticated_client.post(
        "/api/tasks",
        json={
            "prompt": "需要执行的真实任务",
            "project_id": project["id"],
            "execution_kind": "task",
            "start_immediately": True,
        },
    )
    assert task.status_code == 201


def test_project_upload_rejects_mime_spoofing(authenticated_client):
    project = authenticated_client.post("/api/projects", json={"name": "文件校验项目"}).json()
    response = authenticated_client.post(
        f"/api/projects/{project['id']}/files",
        files={"upload": ("fake.pdf", b"this is not a pdf", "application/pdf")},
    )
    assert response.status_code == 415


def test_default_project_recovers_task_submission(authenticated_client):
    projects = authenticated_client.get("/api/projects")
    assert projects.status_code == 200
    writable = projects.json()["items"]
    assert writable
    assert writable[0]["current_user_role"] == "OWNER"

    task = authenticated_client.post(
        "/api/tasks",
        json={
            "prompt": "验证默认项目任务请求",
            "execution_kind": "task",
            "start_immediately": False,
            "client_request_id": "default-project-request-1234",
        },
    )
    assert task.status_code == 201
    assert task.json()["project_id"] == writable[0]["id"]


def test_archived_project_is_listed_and_can_be_restored(authenticated_client):
    project = authenticated_client.post(
        "/api/projects",
        json={"name": "待归档项目", "description": "归档空间回归测试"},
    ).json()

    archived = authenticated_client.post(f"/api/projects/{project['id']}/archive")
    assert archived.status_code == 200
    assert archived.json()["archived_at"]

    visible = authenticated_client.get("/api/projects").json()["items"]
    assert all(item["id"] != project["id"] for item in visible)

    archived_items = authenticated_client.get(
        "/api/projects",
        params={"include_archived": True},
    ).json()["items"]
    assert any(
        item["id"] == project["id"] and item["archived_at"]
        for item in archived_items
    )

    restored = authenticated_client.post(f"/api/projects/{project['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    assert authenticated_client.get(f"/api/projects/{project['id']}").status_code == 200
