import pytest

from app.agent.agent_scope import (
    AgentScopeError,
    build_agent_scope,
    enforce_tool_scope,
)


def test_scope_guidance_uses_task_root_relative_python_paths():
    scope = build_agent_scope(
        node_key="paper_2",
        role="document",
        dependency_keys=[],
        worker_count=3,
    )
    guidance = scope.guidance()
    assert "working directory is the task root" in guidance
    assert "never prefix them again with workspace/" in guidance


def test_parallel_workers_have_separate_private_roots():
    first = build_agent_scope(
        node_key="paper_1",
        role="document",
        dependency_keys=[],
        worker_count=3,
    )
    second = build_agent_scope(
        node_key="paper_2",
        role="document",
        dependency_keys=[],
        worker_count=3,
    )
    assert first.workspace == "workspace/agents/paper_1"
    assert second.workspace == "workspace/agents/paper_2"
    assert first.output != second.output
    assert not first.can_read(second.workspace)
    assert not first.can_write(second.output)


def test_worker_can_only_read_declared_dependency_shared_and_output():
    scope = build_agent_scope(
        node_key="paper_1",
        role="document",
        dependency_keys=["research"],
        worker_count=3,
    )
    assert scope.can_read("shared/agents/research/evidence.md")
    assert scope.can_read("output/research/source-list.csv")
    assert not scope.can_read("shared/agents/paper_2/draft.md")
    assert not scope.can_read("workspace/agents/research/private-notes.md")


def test_tool_scope_blocks_cross_agent_write():
    scope = build_agent_scope(
        node_key="paper_1",
        role="document",
        dependency_keys=[],
        worker_count=3,
    )
    with pytest.raises(AgentScopeError, match="超出当前 Agent 可写范围"):
        enforce_tool_scope(
            "write_text",
            {"path": "workspace/agents/paper_2/create_output.py", "content": "x"},
            scope,
        )


def test_tool_scope_requires_python_in_private_workspace():
    scope = build_agent_scope(
        node_key="paper_1",
        role="document",
        dependency_keys=[],
        worker_count=3,
    )
    accepted = enforce_tool_scope(
        "run_python",
        {"script": "workspace/agents/paper_1/create_output.py"},
        scope,
    )
    assert accepted["script"].endswith("paper_1/create_output.py")
    with pytest.raises(AgentScopeError, match="超出当前 Agent 可读范围"):
        enforce_tool_scope(
            "run_python",
            {"script": "workspace/agents/paper_2/create_output.py"},
            scope,
        )


def test_reviewer_reads_all_outputs_but_writes_only_private_workspace():
    scope = build_agent_scope(
        node_key="review",
        role="reviewer",
        dependency_keys=["paper_1", "paper_2"],
        worker_count=2,
    )
    assert scope.can_read("output/paper_1/exam.docx")
    assert scope.can_read("output/paper_2/exam.docx")
    assert scope.can_write("workspace/agents/review/exam.md")
    assert not scope.can_write("output/paper_1/exam.docx")


def test_unknown_path_tool_cannot_bypass_scope():
    scope = build_agent_scope(
        node_key="paper_1",
        role="document",
        dependency_keys=[],
        worker_count=3,
    )
    with pytest.raises(AgentScopeError, match="不能绕过 Agent 隔离"):
        enforce_tool_scope(
            "future_path_tool",
            {"path": "output/paper_2/result.docx"},
            scope,
        )


def test_data_analyst_cannot_publish_presentation_artifact():
    scope = build_agent_scope(
        node_key="analysis",
        role="data_analyst",
        dependency_keys=[],
        worker_count=2,
    )
    with pytest.raises(AgentScopeError, match="不得生成演示文稿"):
        enforce_tool_scope(
            "copy_file",
            {
                "source": "shared/agents/analysis/analysis.json",
                "target": "output/analysis/report.pptx",
            },
            scope,
        )
