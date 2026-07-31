from datetime import datetime, timezone
from types import SimpleNamespace

import httpx

from app.agent.skill_manager_client import SkillManagerClient
from app.agent.skill_manager_client import SkillInstallResult, SkillRemoveResult


def test_admin_can_request_scanned_skill_install(authenticated_client, monkeypatch):
    monkeypatch.setattr(
        "app.api.skills.SkillManagerClient.scan_install",
        lambda _self, url: SkillInstallResult(
            name="safe-demo",
            source="https://github.com/example/safe-demo",
            source_ref="a" * 40,
            risk_score=10,
            risk_severity="LOW",
            recommendation="ALLOW",
            finding_count=0,
            scan_mode="static-only",
            installed=True,
        ),
    )

    response = authenticated_client.post(
        "/api/skills/install",
        json={"url": "https://github.com/example/safe-demo"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "safe-demo"
    assert response.json()["risk_score"] == 10


def test_admin_can_remove_skill_to_recoverable_trash(authenticated_client, monkeypatch):
    monkeypatch.setattr(
        "app.api.skills.SkillManagerClient.remove",
        lambda _self, name: SkillRemoveResult(
            name=name,
            removed=True,
            recoverable=True,
            trash_id=f"{name}-20260731T120000Z-deadbeef",
            removed_at=datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc),
        ),
    )

    response = authenticated_client.delete("/api/skills/safe-demo")

    assert response.status_code == 200
    assert response.json()["name"] == "safe-demo"
    assert response.json()["removed"] is True
    assert response.json()["recoverable"] is True


def test_skill_manager_client_requests_recoverable_remove():
    def handler(request: httpx.Request):
        assert request.method == "DELETE"
        assert request.url.path == "/v1/skills/safe-demo"
        assert request.headers["X-Skill-Manager-Secret"] == "s" * 32
        return httpx.Response(
            200,
            json={
                "name": "safe-demo",
                "removed": True,
                "recoverable": True,
                "trash_id": "safe-demo-20260731T120000Z-deadbeef",
                "removed_at": "2026-07-31T12:00:00Z",
            },
        )

    client = SkillManagerClient(
        settings=SimpleNamespace(
            skill_manager_url="http://skill-manager:8200",
            skill_manager_timeout_seconds=300,
            skill_manager_shared_secret="s" * 32,
        ),
        transport=httpx.MockTransport(handler),
    )

    result = client.remove("safe-demo")

    assert result.name == "safe-demo"
    assert result.recoverable is True
    assert result.removed_at == datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)
