from app.agent.skill_manager_client import SkillInstallResult


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
