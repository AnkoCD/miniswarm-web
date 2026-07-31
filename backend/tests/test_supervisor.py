from app.agent.supervisor import SupervisorDecision
from app.db import SessionLocal
from app.models import NodeStatus, Task, TaskBriefVersion, TaskDirective, TaskMessage, TaskNode, TaskStatus, User
from app.worker.tasks import supervise_message_task


def test_active_task_auto_message_is_queued_for_supervisor(authenticated_client, monkeypatch):
    queued: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        "app.api.tasks.supervise_message_task.apply_async",
        lambda args, queue: queued.append((args[0], args[1], queue)),
    )
    task = authenticated_client.post(
        "/api/tasks",
        json={"prompt": "创建报告", "execution_kind": "task", "start_immediately": False},
    ).json()
    with SessionLocal() as db:
        stored = db.get(Task, task["id"])
        stored.status = TaskStatus.RUNNING
        db.commit()

    response = authenticated_client.post(
        f"/api/tasks/{task['id']}/messages",
        json={"content": "把标题改成七月月报", "mode": "auto"},
    )
    assert response.status_code == 202
    assert response.json()["mode"] == "supervisor"
    supervision = authenticated_client.get(f"/api/tasks/{task['id']}/supervision").json()
    assert supervision["status"] == "QUEUED"
    assert supervision["directives"][0]["status"] == "PENDING"
    assert queued[0][0] == task["id"]
    assert queued[0][2] == "supervisor"


def test_supervisor_merges_directive_and_requeues_completed_node(monkeypatch):
    monkeypatch.setattr(
        "app.worker.tasks.Supervisor.analyze",
        lambda *args, **kwargs: (
            SupervisorDecision(
                kind="directive",
                summary="标题改成七月月报",
                affected_node_keys=["work"],
            ),
            None,
        ),
    )
    dispatched: list[str] = []
    monkeypatch.setattr(
        "app.worker.tasks.run_task.apply_async",
        lambda args, queue: dispatched.append(args[0]),
    )
    with SessionLocal() as db:
        user = db.query(User).filter_by(username="admin").one()
        task = Task(
            owner_id=user.id,
            title="报告",
            prompt="创建报告",
            execution_kind="task",
            status=TaskStatus.RUNNING,
        )
        db.add(task)
        db.flush()
        message = TaskMessage(task_id=task.id, role="user", mode="supervisor", content="把标题改成七月月报")
        db.add(message)
        db.flush()
        directive = TaskDirective(task_id=task.id, message_id=message.id)
        node = TaskNode(
            task_id=task.id,
            node_key="work",
            role="document",
            title="制作报告",
            instructions="生成报告",
            depends_on=[],
            status=NodeStatus.SUCCEEDED,
        )
        reviewer = TaskNode(
            task_id=task.id,
            node_key="review",
            role="reviewer",
            title="检查报告",
            instructions="检查报告",
            depends_on=["work"],
            status=NodeStatus.PENDING,
        )
        db.add_all([directive, node, reviewer])
        db.commit()
        task_id, directive_id, node_id = task.id, directive.id, node.id

    result = supervise_message_task.run(task_id, directive_id)
    assert result["status"] == "MERGED"
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        directive = db.get(TaskDirective, directive_id)
        node = db.get(TaskNode, node_id)
        brief = db.query(TaskBriefVersion).filter_by(task_id=task_id, version=2).one()
        assert task.brief_version == 2
        assert directive.status == "MERGED"
        assert node.status == NodeStatus.READY
        assert node.target_brief_version == 2
        assert "七月月报" in node.instructions
        assert brief.change_summary == "标题改成七月月报"
    assert dispatched == [task_id]


def test_executor_applies_only_new_brief_delta():
    from app.agent.executor import AgentExecutor

    with SessionLocal() as db:
        user = db.query(User).filter_by(username="admin").one()
        task = Task(owner_id=user.id, title="任务", prompt="初始要求", status=TaskStatus.RUNNING, brief_version=2)
        db.add(task)
        db.flush()
        node = TaskNode(
            task_id=task.id,
            node_key="work",
            role="document",
            title="制作",
            instructions="制作",
            depends_on=[],
            status=NodeStatus.RUNNING,
            target_brief_version=2,
            applied_brief_version=1,
        )
        db.add_all([
            node,
            TaskBriefVersion(
                task_id=task.id,
                version=2,
                goal="初始要求",
                acceptance_criteria=["使用蓝色"],
                change_summary="主色改成蓝色",
            ),
        ])
        db.commit()
        messages: list[dict] = []
        assert AgentExecutor._apply_brief_updates(db, task, node, messages)
        assert node.applied_brief_version == 2
        assert "主色改成蓝色" in messages[0]["content"]
