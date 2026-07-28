from types import SimpleNamespace

from app.agent.skill_registry import (
    list_installed_skills,
    load_ppt_skill_prompt,
    load_task_skill_prompt,
    ppt_skill_applies,
)
from app.core.config import Settings


def test_ppt_skill_is_automatically_loaded_for_document_role(tmp_path):
    skill_root = tmp_path / "skills" / "guizang-ppt-skill"
    skill_root.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text("# Official workflow", encoding="utf-8")
    settings = Settings(
        app_env="test",
        jwt_secret="test-secret-that-is-long-enough",
        runner_shared_secret="test-runner-secret-that-is-long-enough",
        skills_root=tmp_path / "skills",
    )
    prompt = load_ppt_skill_prompt(settings, "请生成瑞士风 PPT", "document")
    assert "Official workflow" in prompt
    assert "validate_swiss_deck" in prompt


def test_ppt_skill_is_not_loaded_for_unrelated_reader_task():
    assert not ppt_skill_applies("总结这份文本", "reader")


def test_generic_skill_modes_and_auto_selection(tmp_path):
    skills_root = tmp_path / "skills"
    for name, description in (
        ("anysearch", "Real-time web search"),
        ("humanizer-zh", "Natural Chinese writing"),
        ("docx", "Word document workflow"),
        ("pdf", "PDF workflow"),
        ("xlsx", "Spreadsheet workflow"),
    ):
        root = skills_root / name
        root.mkdir(parents=True)
        (root / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n\n# Workflow",
            encoding="utf-8",
        )
    settings = Settings(
        app_env="test",
        jwt_secret="test-secret-that-is-long-enough",
        runner_shared_secret="test-runner-secret-that-is-long-enough",
        skills_root=skills_root,
    )
    task = SimpleNamespace(skill_mode="auto", selected_skills=[])
    prompt, names = load_task_skill_prompt(
        settings, task, "请联网搜索最新消息", "researcher"
    )
    assert names == ["anysearch"]
    assert "Real-time web search" in prompt

    task.skill_mode = "manual"
    task.selected_skills = ["humanizer-zh"]
    _, names = load_task_skill_prompt(settings, task, "搜索新闻", "document")
    assert names == ["humanizer-zh"]

    task.skill_mode = "off"
    assert load_task_skill_prompt(settings, task, "搜索新闻", "researcher") == ("", [])
    assert {item.name for item in list_installed_skills(settings)} == {
        "anysearch",
        "docx",
        "humanizer-zh",
        "pdf",
        "xlsx",
    }


def test_office_skills_auto_select_by_file_type(tmp_path):
    skills_root = tmp_path / "skills"
    for name in ("docx", "pdf", "xlsx"):
        root = skills_root / name
        root.mkdir(parents=True)
        (root / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {name} workflow\n---\n",
            encoding="utf-8",
        )
    settings = Settings(
        app_env="test",
        jwt_secret="test-secret-that-is-long-enough",
        runner_shared_secret="test-runner-secret-that-is-long-enough",
        skills_root=skills_root,
    )
    task = SimpleNamespace(skill_mode="auto", selected_skills=[])
    _, docx_names = load_task_skill_prompt(
        settings, task, "创建 output/report.docx", "document"
    )
    _, pdf_names = load_task_skill_prompt(
        settings, task, "合并两个 PDF 文件", "document"
    )
    _, xlsx_names = load_task_skill_prompt(
        settings, task, "分析 sales.xlsx 并输出 Excel", "data_analyst"
    )
    assert docx_names == ["docx"]
    assert pdf_names == ["pdf"]
    assert xlsx_names == ["xlsx"]


def test_huashu_design_auto_selects_for_visual_design_and_stays_safe(tmp_path):
    skills_root = tmp_path / "skills"
    root = skills_root / "huashu-design"
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(
        "---\nname: huashu-design\ndescription: Visual design workflow\n---\n\n# Workflow",
        encoding="utf-8",
    )
    settings = Settings(
        app_env="test",
        jwt_secret="test-secret-that-is-long-enough",
        runner_shared_secret="test-runner-secret-that-is-long-enough",
        skills_root=skills_root,
    )
    task = SimpleNamespace(skill_mode="auto", selected_skills=[])

    prompt, names = load_task_skill_prompt(
        settings, task, "制作一个高保真原型并进行视觉评审", "coder"
    )

    assert names == ["huashu-design"]
    assert "不得执行 scripts/cloud" in prompt
    assert "Visual design workflow" in prompt
