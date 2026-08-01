from types import SimpleNamespace

from app.agent.skill_registry import select_task_skills


def _settings(tmp_path):
    skill_root = tmp_path / "skills"
    for name in ("pptx", "xlsx", "guizang-ppt-skill"):
        (skill_root / name).mkdir(parents=True, exist_ok=True)
        (skill_root / name / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: test skill\n---\ncontent\n",
            encoding="utf-8",
        )
    return SimpleNamespace(
        skills_root=skill_root,
        max_skills_per_node=3,
        max_skill_context_chars=120_000,
    )


def _task(selected_skills, skill_mode="auto"):
    return SimpleNamespace(selected_skills=selected_skills, skill_mode=skill_mode)


def test_explicit_pptx_skill_is_blocked_for_data_analyst(tmp_path):
    settings = _settings(tmp_path)
    selected = select_task_skills(
        settings,
        _task(["pptx", "xlsx"]),
        "请分析考试成绩，做一份成绩分析报告ppt",
        "data_analyst",
    )
    names = [item.name for item in selected]
    assert "xlsx" in names
    assert "pptx" not in names
    assert "guizang-ppt-skill" not in names


def test_explicit_pptx_skill_is_allowed_for_document(tmp_path):
    settings = _settings(tmp_path)
    selected = select_task_skills(
        settings,
        _task(["pptx", "xlsx"]),
        "请分析考试成绩，做一份成绩分析报告ppt",
        "document",
    )
    names = [item.name for item in selected]
    assert "pptx" in names
    assert "guizang-ppt-skill" in names


def test_explicit_pptx_skill_is_allowed_for_reviewer(tmp_path):
    settings = _settings(tmp_path)
    selected = select_task_skills(
        settings,
        _task(["pptx"]),
        "检查PPT报告",
        "reviewer",
    )
    assert "pptx" in [item.name for item in selected]


def test_manual_mode_still_respects_role_boundary(tmp_path):
    settings = _settings(tmp_path)
    selected = select_task_skills(
        settings,
        _task(["pptx"], skill_mode="manual"),
        "分析数据",
        "data_analyst",
    )
    assert selected == []


def test_manual_ppt_skill_alias_is_blocked_for_data_analyst(tmp_path):
    settings = _settings(tmp_path)
    selected = select_task_skills(
        settings,
        _task(["guizang-ppt-skill", "pptx", "xlsx"], skill_mode="manual"),
        "请分析考试成绩，最终由下游节点制作 PPT",
        "data_analyst",
    )
    assert [item.name for item in selected] == ["xlsx"]
