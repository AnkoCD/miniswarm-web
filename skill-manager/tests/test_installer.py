from pathlib import Path

import pytest

from skill_manager.installer import SkillInstallError, _find_skill_root, parse_github_url


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
