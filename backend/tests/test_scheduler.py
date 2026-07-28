from app.db import SessionLocal
from app.core.config import Settings
from app.models import Artifact, NodeStatus, Task, TaskNode, TaskStatus, ToolCall, ToolCallStatus, User
from app.storage import task_root
from app.worker.tasks import _schedule_plan


def test_scheduler_dispatches_independent_nodes_in_parallel(monkeypatch):
    dispatched: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        "app.worker.tasks.execute_node_task.apply_async",
        lambda args, queue: dispatched.append((args[0], args[1], queue)),
    )
    with SessionLocal() as db:
        user = db.query(User).filter_by(username="admin").one()
        task = Task(owner_id=user.id, title="并行", prompt="分析两个文件", status=TaskStatus.RUNNING)
        db.add(task)
        db.flush()
        first = TaskNode(
            task_id=task.id, node_key="a", role="reader", title="读取 A",
            instructions="读取 A", depends_on=[], weight=40, status=NodeStatus.READY,
        )
        second = TaskNode(
            task_id=task.id, node_key="b", role="reader", title="读取 B",
            instructions="读取 B", depends_on=[], weight=40, status=NodeStatus.READY,
        )
        review = TaskNode(
            task_id=task.id, node_key="review", role="reviewer", title="检查",
            instructions="检查两个结果", depends_on=["a", "b"], weight=20, status=NodeStatus.PENDING,
        )
        db.add_all([first, second, review])
        db.commit()
        task_id = task.id
        first_id, second_id, review_id = first.id, second.id, review.id

    result = _schedule_plan(task_id)
    assert result == {"status": "dispatched", "count": 2}
    assert {item[1] for item in dispatched} == {first_id, second_id}
    assert all(item[2] == "agent" for item in dispatched)

    dispatched.clear()
    with SessionLocal() as db:
        db.get(TaskNode, first_id).status = NodeStatus.SUCCEEDED
        db.get(TaskNode, second_id).status = NodeStatus.SUCCEEDED
        db.commit()
    result = _schedule_plan(task_id)
    assert result == {"status": "dispatched", "count": 1}
    assert dispatched[0][1] == review_id


def test_scheduler_allows_only_one_rework(monkeypatch):
    dispatched: list[str] = []
    monkeypatch.setattr(
        "app.worker.tasks.execute_node_task.apply_async",
        lambda args, queue: dispatched.append(args[1]),
    )
    with SessionLocal() as db:
        user = db.query(User).filter_by(username="admin").one()
        task = Task(owner_id=user.id, title="返工", prompt="生成报告", status=TaskStatus.REVIEWING)
        db.add(task)
        db.flush()
        producer = TaskNode(
            task_id=task.id, node_key="work", role="document", title="生成报告",
            instructions="生成正文", depends_on=[], weight=80, status=NodeStatus.SUCCEEDED,
        )
        db.add(producer)
        db.flush()
        reviewer = TaskNode(
            task_id=task.id, node_key="review", role="reviewer", title="检查",
            instructions="检查报告", depends_on=["work"], weight=20, status=NodeStatus.FAILED,
            attempt=1, result_summary="REWORK_REQUIRED: 增加结论章节",
        )
        db.add(reviewer)
        db.commit()
        task_id, producer_id = task.id, producer.id

    result = _schedule_plan(task_id)
    assert result == {"status": "dispatched", "count": 1}
    assert dispatched == [producer_id]
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        producer = db.get(TaskNode, producer_id)
        assert task.review_retries == 1
        assert "增加结论章节" in producer.instructions


def test_scheduler_requires_real_reviewer_inspection_before_delivery(tmp_path, monkeypatch):
    settings = Settings(
        app_env="test",
        jwt_secret="test-secret-that-is-long-enough",
        data_root=tmp_path,
    )
    monkeypatch.setattr("app.quality.get_settings", lambda: settings)
    monkeypatch.setattr("app.worker.tasks.get_settings", lambda: settings)
    dispatched: list[str] = []
    monkeypatch.setattr(
        "app.worker.tasks.execute_node_task.apply_async",
        lambda args, queue: dispatched.append(args[1]),
    )
    with SessionLocal() as db:
        user = db.query(User).filter_by(username="admin").one()
        task = Task(
            owner_id=user.id,
            title="可靠交付",
            prompt="生成一份 PPTX 演示文稿",
            task_type="document",
            status=TaskStatus.REVIEWING,
        )
        db.add(task)
        db.flush()
        producer = TaskNode(
            task_id=task.id, node_key="work", role="document", title="制作",
            instructions="制作 PPTX", depends_on=[], weight=80, status=NodeStatus.SUCCEEDED,
        )
        reviewer = TaskNode(
            task_id=task.id, node_key="review", role="reviewer", title="检查",
            instructions="检查 PPTX", depends_on=["work"], weight=20, status=NodeStatus.SUCCEEDED,
        )
        db.add_all([producer, reviewer])
        db.flush()
        output = task_root(task.owner_id, task.id, settings) / "output" / "report.pptx"
        output.write_bytes(b"real-non-empty-pptx-placeholder-for-gate")
        artifact = Artifact(
            task_id=task.id, node_id=producer.id, filename="report.pptx",
            relative_path="output/report.pptx", size=output.stat().st_size,
            is_final=True, inspection_status="READY",
        )
        db.add(artifact)
        db.commit()
        task_id, reviewer_id, artifact_id = task.id, reviewer.id, artifact.id

    first = _schedule_plan(task_id)
    assert first == {"status": "dispatched", "count": 1}
    assert dispatched == [reviewer_id]
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        reviewer = db.get(TaskNode, reviewer_id)
        assert task.review_retries == 1
        assert task.status == TaskStatus.REVIEWING
        assert reviewer.status == NodeStatus.QUEUED
        reviewer.status = NodeStatus.SUCCEEDED
        db.add(
            ToolCall(
                task_id=task_id, node_id=reviewer_id, tool_name="inspect_document",
                arguments={"path": "output/report.pptx"}, status=ToolCallStatus.SUCCEEDED,
            )
        )
        db.commit()

    second = _schedule_plan(task_id)
    assert second == {"status": "succeeded"}
    with SessionLocal() as db:
        assert db.get(Task, task_id).status == TaskStatus.SUCCEEDED
        assert db.get(Artifact, artifact_id).inspection_status == "VERIFIED"
