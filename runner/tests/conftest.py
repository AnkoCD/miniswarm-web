import os

os.environ["RUNNER_SHARED_SECRET"] = "test-runner-secret-that-is-long-enough"

import pytest

from runner_app.config import RunnerSettings, get_settings


@pytest.fixture
def settings(tmp_path):
    skill_root = tmp_path / "skills" / "guizang-ppt-skill"
    (skill_root / "assets").mkdir(parents=True)
    (skill_root / "scripts").mkdir()
    (skill_root / "SKILL.md").write_text("# Test PPT Skill", encoding="utf-8")
    (skill_root / "assets" / "template.html").write_text("<html></html>", encoding="utf-8")
    (skill_root / "scripts" / "validate-swiss-deck.mjs").write_text(
        "console.log('ok')", encoding="utf-8"
    )
    anysearch_root = tmp_path / "skills" / "anysearch"
    (anysearch_root / "scripts").mkdir(parents=True)
    (anysearch_root / "SKILL.md").write_text("# AnySearch", encoding="utf-8")
    (anysearch_root / "scripts" / "anysearch_cli.js").write_text(
        "console.log('search')", encoding="utf-8"
    )
    markitdown_root = tmp_path / "skills" / "markitdown"
    markitdown_root.mkdir(parents=True)
    (markitdown_root / "SKILL.md").write_text("# MarkItDown", encoding="utf-8")
    value = RunnerSettings(
        data_root=tmp_path,
        skills_root=tmp_path / "skills",
        shared_secret="test-runner-secret-that-is-long-enough",
        max_text_bytes=1024,
    )
    get_settings.cache_clear()
    return value
