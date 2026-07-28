from app.agent.tools import tool_definitions_for_skills


def _names(skills, *, reviewer=False, allow_skill_install=False):
    return {
        item["function"]["name"]
        for item in tool_definitions_for_skills(
            skills,
            reviewer=reviewer,
            allow_skill_install=allow_skill_install,
        )
    }


def test_office_skills_expose_safe_document_tools():
    for skill in ("docx", "pdf", "xlsx"):
        names = _names([skill])
        assert "read_skill_file" in names
        assert "run_python" in names
        assert "inspect_document" in names
        assert "convert_document" in names
        assert "convert_to_markdown" in names
        assert "anysearch" not in names


def test_reviewer_remains_read_only_with_office_skill():
    names = _names(["pdf"], reviewer=True)
    assert "inspect_document" in names
    assert "run_python" not in names
    assert "convert_document" not in names
    assert "convert_to_markdown" in names


def test_huashu_design_exposes_only_existing_safe_skill_tools():
    names = _names(["huashu-design"])
    assert "read_skill_file" in names
    assert "copy_skill_file" in names
    assert "run_python" in names
    assert "anysearch" not in names
    assert "validate_swiss_deck" not in names


def test_skill_install_tool_is_admin_gated_and_never_exposed_to_reviewer():
    assert "install_skill_from_github" not in _names([])
    assert "install_skill_from_github" in _names([], allow_skill_install=True)
    assert "install_skill_from_github" not in _names(
        [],
        reviewer=True,
        allow_skill_install=True,
    )
