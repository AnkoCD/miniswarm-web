import json

from app.agent.deepseek import ChatResult, DeepSeekError, ModelUsage
from app.agent.interaction_router import resolve_interaction_mode
from app.core.config import Settings
from app.models import Task, TaskStatus


USAGE = ModelUsage(
    prompt_tokens=12,
    completion_tokens=4,
    cache_hit_tokens=0,
    duration_ms=8,
)


class FakeRouterClient:
    def __init__(self, mode: str):
        self.mode = mode

    def chat(self, **kwargs):
        return ChatResult(message={"content": json.dumps({"mode": self.mode})}, usage=USAGE)


class UnavailableRouterClient:
    def chat(self, **kwargs):
        raise DeepSeekError("暂时不可用")


def test_model_routes_new_request_to_task():
    route = resolve_interaction_mode(
        "请分析数据并生成报告文件",
        "auto",
        settings=Settings(deepseek_api_key="test"),
        client=FakeRouterClient("task"),
    )
    assert route.mode == "task"
    assert route.source == "model"
    assert route.usage == USAGE


def test_terminal_task_only_allows_chat_or_revision():
    task = Task(
        status=TaskStatus.SUCCEEDED,
        execution_kind="task",
        current_revision=0,
        model_mode="auto",
    )
    route = resolve_interaction_mode(
        "请把报告文件的标题修改为新版",
        "auto",
        task=task,
        settings=Settings(deepseek_api_key="test"),
        client=FakeRouterClient("task"),
    )
    assert route.mode == "revise"
    assert route.source == "fallback"


def test_unavailable_model_falls_back_to_safe_chat():
    route = resolve_interaction_mode(
        "这个结论是什么意思？",
        "auto",
        settings=Settings(deepseek_api_key="test"),
        client=UnavailableRouterClient(),
    )
    assert route.mode == "chat"
    assert route.source == "fallback"


def test_running_task_is_always_chat():
    task = Task(status=TaskStatus.RUNNING, execution_kind="task", current_revision=0)
    route = resolve_interaction_mode(
        "修改输出文件",
        "auto",
        task=task,
        settings=Settings(deepseek_api_key="test"),
        client=FakeRouterClient("revise"),
    )
    assert route.mode == "chat"
