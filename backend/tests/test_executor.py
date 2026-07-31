from app.agent.deepseek import ChatResult, ModelUsage
from app.agent.executor import AgentExecutor
from app.agent.runner_client import RunnerResult
from app.core.config import Settings
from app.db import SessionLocal
from app.models import Approval, NodeStatus, Task, TaskNode, TaskStatus, ToolCall, ToolCallStatus, User
from app.storage import task_root


class FakeModel:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        message = next(self.messages)
        if isinstance(message, ChatResult):
            return message
        return ChatResult(
            message=message,
            usage=ModelUsage(prompt_tokens=10, completion_tokens=5, cache_hit_tokens=0, duration_ms=1),
        )


class FakeRunner:
    def __init__(self):
        self.calls = []

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        return RunnerResult(ok=True, summary="文件已列出", data={"items": []})


def make_task_and_node(
    db,
    *,
    tool_role="reader",
    model_mode="auto",
    execution_mode="standard",
    autonomy_mode="safe",
):
    user = db.query(User).filter_by(username="admin").one()
    task = Task(
        owner_id=user.id,
        title="测试",
        prompt="列出文件",
        status=TaskStatus.RUNNING,
        model_mode=model_mode,
        execution_mode=execution_mode,
        autonomy_mode=autonomy_mode,
    )
    db.add(task)
    db.flush()
    node = TaskNode(
        task_id=task.id, node_key="work", role=tool_role, title="处理文件",
        instructions="检查任务文件", depends_on=[], weight=100, status=NodeStatus.READY,
    )
    db.add(node)
    db.commit()
    return task, node


def config(tmp_path):
    return Settings(
        app_env="test",
        jwt_secret="test-secret-that-is-long-enough",
        data_root=tmp_path,
        runner_shared_secret="test-runner-secret-that-is-long-enough",
    )


def test_executor_runs_tool_then_finishes(tmp_path):
    model = FakeModel([
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "private",
            "tool_calls": [{"id": "call-1", "function": {"name": "list_files", "arguments": "{\"path\":\".\"}"}}],
        },
        {"role": "assistant", "content": "已检查文件", "reasoning_content": "private", "tool_calls": None},
    ])
    runner = FakeRunner()
    with SessionLocal() as db:
        task, node = make_task_and_node(db)
        outcome = AgentExecutor(model, runner, config(tmp_path)).run_node(db, task, node)
        assert outcome.status == "succeeded"
        assert node.status == NodeStatus.SUCCEEDED
        call = db.query(ToolCall).filter_by(task_id=task.id).one()
        assert call.status == ToolCallStatus.SUCCEEDED
        assert len(runner.calls) == 1


def test_executor_pauses_for_risky_tool(tmp_path):
    model = FakeModel([
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call-2", "function": {"name": "move_to_trash", "arguments": "{\"path\":\"workspace/a.txt\"}"}}],
        }
    ])
    runner = FakeRunner()
    with SessionLocal() as db:
        task, node = make_task_and_node(db, tool_role="file_worker")
        outcome = AgentExecutor(model, runner, config(tmp_path)).run_node(db, task, node)
        assert outcome.status == "waiting"
        assert node.status == NodeStatus.WAITING
        assert db.query(Approval).filter_by(task_id=task.id).count() == 1
        assert not runner.calls


def test_yolo_auto_approves_generated_file_overwrite(tmp_path):
    model = FakeModel([
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call-yolo",
                "function": {
                    "name": "write_text",
                    "arguments": '{"path":"workspace/a.txt","content":"new"}',
                },
            }],
        },
        {"role": "assistant", "content": "已更新", "tool_calls": None},
    ])
    runner = FakeRunner()
    settings = config(tmp_path)
    with SessionLocal() as db:
        task, node = make_task_and_node(
            db,
            tool_role="file_worker",
            autonomy_mode="yolo",
        )
        root = task_root(task.owner_id, task.id, settings)
        (root / "workspace" / "a.txt").write_text("old", encoding="utf-8")
        outcome = AgentExecutor(model, runner, settings).run_node(db, task, node)
        assert outcome.status == "succeeded"
        assert runner.calls[0]["approval_granted"] is True
        assert db.query(Approval).filter_by(task_id=task.id).count() == 0


def test_yolo_still_requires_trash_approval(tmp_path):
    model = FakeModel([
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call-yolo-trash",
                "function": {
                    "name": "move_to_trash",
                    "arguments": '{"path":"workspace/a.txt"}',
                },
            }],
        }
    ])
    with SessionLocal() as db:
        task, node = make_task_and_node(
            db,
            tool_role="file_worker",
            autonomy_mode="yolo",
        )
        outcome = AgentExecutor(model, FakeRunner(), config(tmp_path)).run_node(db, task, node)
        assert outcome.status == "waiting"
        assert db.query(Approval).filter_by(task_id=task.id).count() == 1


def test_tool_limit_is_scoped_to_current_revision(tmp_path):
    model = FakeModel([
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call-current-revision",
                "function": {"name": "list_files", "arguments": '{"path":"."}'},
            }],
        },
        {"role": "assistant", "content": "当前修订完成", "tool_calls": None},
    ])
    with SessionLocal() as db:
        task, node = make_task_and_node(db)
        task.current_revision = 1
        node.revision = 1
        old_node = TaskNode(
            task_id=task.id,
            revision=0,
            node_key="old",
            role="reader",
            title="旧修订",
            instructions="旧修订",
            depends_on=[],
            weight=100,
            status=NodeStatus.FAILED,
        )
        db.add(old_node)
        db.flush()
        db.add_all([
            ToolCall(
                task_id=task.id,
                node_id=old_node.id,
                tool_name="list_files",
                arguments={"path": "."},
                status=ToolCallStatus.SUCCEEDED,
            )
            for _ in range(60)
        ])
        db.commit()
        outcome = AgentExecutor(model, FakeRunner(), config(tmp_path)).run_node(db, task, node)
        assert outcome.status == "succeeded"


def test_reviewer_returns_structured_rework(tmp_path):
    model = FakeModel([
        {
            "role": "assistant",
            "content": '{"verdict":"rework","summary":"文件为空","instructions":"补充正文"}',
            "tool_calls": None,
        }
    ])
    with SessionLocal() as db:
        task, node = make_task_and_node(db, tool_role="reviewer")
        outcome = AgentExecutor(model, FakeRunner(), config(tmp_path)).run_node(db, task, node)
        assert outcome.status == "failed"
        assert node.result_summary == "REWORK_REQUIRED: 补充正文"


def test_executor_uses_task_model_and_thinking_choice(tmp_path):
    model = FakeModel([
        {"role": "assistant", "content": "已完成", "tool_calls": None},
    ])
    with SessionLocal() as db:
        task, node = make_task_and_node(
            db,
            model_mode="deepseek-v4-flash",
            execution_mode="deep",
        )
        outcome = AgentExecutor(model, FakeRunner(), config(tmp_path)).run_node(db, task, node)
        assert outcome.status == "succeeded"
        assert model.calls[0]["model"] == "deepseek-v4-flash"
        assert model.calls[0]["thinking"] is True
        assert model.calls[0]["max_tokens"] is None


def test_executor_injects_installed_ppt_skill(tmp_path):
    skill_root = tmp_path / "skills" / "guizang-ppt-skill"
    skill_root.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text("# Loaded PPT workflow", encoding="utf-8")
    model = FakeModel([
        {"role": "assistant", "content": "已完成", "tool_calls": None},
    ])
    settings = config(tmp_path)
    settings.skills_root = tmp_path / "skills"
    with SessionLocal() as db:
        task, node = make_task_and_node(db, tool_role="document")
        task.prompt = "制作瑞士风 PPT"
        node.instructions = "生成幻灯片"
        db.commit()
        AgentExecutor(model, FakeRunner(), settings).run_node(db, task, node)
        assert "Loaded PPT workflow" in model.calls[0]["messages"][0]["content"]
