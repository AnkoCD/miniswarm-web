import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from runner_app.agent_scope import RunnerScopeError, enforce_request_scope


def scope_payload(node="paper_1"):
    return {
        "node_key": node,
        "role": "document",
        "workspace": f"workspace/agents/{node}",
        "shared": f"shared/agents/{node}",
        "output": f"output/{node}",
        "readable_roots": [
            "input",
            f"workspace/agents/{node}",
            f"shared/agents/{node}",
            f"output/{node}",
        ],
        "writable_roots": [
            f"workspace/agents/{node}",
            f"shared/agents/{node}",
            f"output/{node}",
        ],
    }


def request(tool, arguments, scope=None):
    return SimpleNamespace(tool=tool, arguments=arguments, agent_scope=scope)


def test_runner_rechecks_cross_agent_paths():
    with pytest.raises(RunnerScopeError, match="跨 Agent"):
        enforce_request_scope(
            request(
                "write_text",
                {"path": "output/paper_2/exam.docx", "content": "x"},
                scope_payload(),
            )
        )


def test_runner_blocks_data_analyst_presentation_output():
    scope = scope_payload("analysis")
    scope["role"] = "data_analyst"
    with pytest.raises(RunnerScopeError, match="不得生成演示文稿"):
        enforce_request_scope(
            request(
                "copy_file",
                {
                    "source": "shared/agents/analysis/analysis.json",
                    "target": "output/analysis/report.pptx",
                },
                scope,
            )
        )


def test_python_audit_sandbox_blocks_other_agent(tmp_path):
    task = tmp_path / "data/users/u/tasks/t"
    own = task / "workspace/agents/paper_1"
    other = task / "workspace/agents/paper_2"
    own.mkdir(parents=True)
    other.mkdir(parents=True)
    (other / "secret.txt").write_text("PRIVATE", encoding="utf-8")
    script = own / "read_other.py"
    script.write_text(
        "from pathlib import Path\nprint(Path('agents/paper_2/secret.txt').read_text())\n",
        encoding="utf-8",
    )
    wrapper = Path(__file__).parents[1] / "runner_app/sandbox_runner.py"
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            str(wrapper),
            "--task-root",
            str(task),
            "--script",
            str(script),
            "--read-roots",
            json.dumps(["input", "workspace/agents/paper_1", "output/paper_1"]),
            "--write-roots",
            json.dumps(["workspace/agents/paper_1", "output/paper_1"]),
        ],
        cwd=task / "workspace",
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 126
    assert "跨 Agent" in completed.stderr


def test_python_audit_sandbox_allows_own_output(tmp_path):
    task = tmp_path / "data/users/u/tasks/t"
    own = task / "workspace/agents/paper_1"
    output = task / "output/paper_1"
    own.mkdir(parents=True)
    output.mkdir(parents=True)
    script = own / "write_own.py"
    script.write_text(
        "from pathlib import Path\nPath('../output/paper_1/result.txt').write_text('ok')\n",
        encoding="utf-8",
    )
    wrapper = Path(__file__).parents[1] / "runner_app/sandbox_runner.py"
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            str(wrapper),
            "--task-root",
            str(task),
            "--script",
            str(script),
            "--read-roots",
            json.dumps(["input", "workspace/agents/paper_1", "output/paper_1"]),
            "--write-roots",
            json.dumps(["workspace/agents/paper_1", "output/paper_1"]),
        ],
        cwd=task / "workspace",
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert (output / "result.txt").read_text() == "ok"


def test_python_audit_sandbox_blocks_data_analyst_presentation(tmp_path):
    task = tmp_path / "data/users/u/tasks/t"
    own = task / "workspace/agents/analysis"
    output = task / "output/analysis"
    own.mkdir(parents=True)
    output.mkdir(parents=True)
    script = own / "write_ppt.py"
    script.write_text(
        "from pathlib import Path\nPath('../output/analysis/report.pptx').write_bytes(b'ppt')\n",
        encoding="utf-8",
    )
    wrapper = Path(__file__).parents[1] / "runner_app/sandbox_runner.py"
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            str(wrapper),
            "--task-root",
            str(task),
            "--script",
            str(script),
            "--read-roots",
            json.dumps(["input", "workspace/agents/analysis", "output/analysis"]),
            "--write-roots",
            json.dumps(["workspace/agents/analysis", "output/analysis"]),
            "--role",
            "data_analyst",
            "--output-root",
            "output/analysis",
        ],
        cwd=task / "workspace",
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 126
    assert "不得生成演示文稿" in completed.stderr
    assert not (output / "report.pptx").exists()
