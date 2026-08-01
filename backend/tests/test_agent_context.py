from app.agent.agent_context import isolated_agent_context
from app.db import SessionLocal
from app.models import Task, TaskBriefVersion, TaskMessage, TaskStatus, User


def test_isolated_agent_context_excludes_assistant_messages():
    with SessionLocal() as db:
        user = db.query(User).filter_by(username="admin").one()
        task = Task(
            owner_id=user.id,
            title="上下文隔离测试",
            prompt="生成三份报告",
            status=TaskStatus.RUNNING,
            brief_version=1,
        )
        db.add(task)
        db.flush()
        db.add_all(
            [
                TaskMessage(
                    task_id=task.id,
                    revision=0,
                    role="user",
                    mode="task",
                    content="三份报告必须采用不同结构",
                    status="COMPLETED",
                ),
                TaskMessage(
                    task_id=task.id,
                    revision=0,
                    role="assistant",
                    mode="task",
                    content="OTHER_AGENT_PRIVATE_DRAFT",
                    status="COMPLETED",
                ),
                TaskBriefVersion(
                    task_id=task.id,
                    version=1,
                    goal="生成三份独立报告",
                    acceptance_criteria=["必须交付三份文件"],
                    change_summary="初始要求",
                ),
            ]
        )
        db.commit()

        context = isolated_agent_context(db, task)

        assert "三份报告必须采用不同结构" in context
        assert "必须交付三份文件" in context
        assert "OTHER_AGENT_PRIVATE_DRAFT" not in context
