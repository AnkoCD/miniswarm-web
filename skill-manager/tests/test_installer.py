from pathlib import Path
from types import SimpleNamespace

import pytest

from skill_manager.installer import (
    SkillInstallError,
    _find_skill_root,
    parse_github_url,
    remove_skill,
)


def test_parse_public_github_skill_path():
    target = parse_github_url("https://github.com/owner/repo/tree/main/skills/demo")
    assert (target.owner, target.repo, target.ref, target.subpath) == (
        "owner",
        "repo",
        "main",
        "skills/demo",
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/owner/repo",
        "https://example.com/owner/repo",
        "https://user:pass@github.com/owner/repo",
        "https://github.com/owner/repo?token=secret",
    ],
)
def test_rejects_untrusted_or_credentialed_urls(url):
    with pytest.raises(SkillInstallError):
        parse_github_url(url)


def test_ambiguous_repository_requires_exact_path(tmp_path: Path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "SKILL.md").write_text("---\nname: a\n---", encoding="utf-8")
    (tmp_path / "b" / "SKILL.md").write_text("---\nname: b\n---", encoding="utf-8")
    with pytest.raises(SkillInstallError, match="多个 Skill"):
        _find_skill_root(tmp_path, "")


def test_remove_skill_moves_directory_to_recoverable_trash(tmp_path: Path):
    skills_root = tmp_path / "skills"
    skill_root = skills_root / "demo-skill"
    skill_root.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Demo\n---\n",
        encoding="utf-8",
    )
    (skill_root / "asset.txt").write_text("preserved", encoding="utf-8")

    result = remove_skill(
        "demo-skill",
        SimpleNamespace(skills_root=skills_root),
    )

    assert result["removed"] is True
    assert result["recoverable"] is True
    assert not skill_root.exists()
    trashed = skills_root / ".trash" / result["trash_id"]
    assert (trashed / "SKILL.md").is_file()
    assert (trashed / "asset.txt").read_text(encoding="utf-8") == "preserved"


@pytest.mark.parametrize("name", ["../demo", ".trash", "Demo", "a/b"])
def test_remove_skill_rejects_invalid_names(tmp_path: Path, name: str):
    with pytest.raises(SkillInstallError, match="名称无效"):
        remove_skill(name, SimpleNamespace(skills_root=tmp_path / "skills"))
