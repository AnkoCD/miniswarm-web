import json

import httpx
import pytest

from app.agent.deepseek import DeepSeekClient, DeepSeekError
from app.agent.planner import Planner, TaskPlan
from app.core.config import Settings


def settings() -> Settings:
    return Settings(
        app_env="test",
        jwt_secret="test-secret-that-is-long-enough",
        deepseek_api_key="secret-test-key",
    )


def test_planner_accepts_valid_dag():
    plan_json = {
        "mode": "swarm",
        "goal": "并行分析两个文件",
        "nodes": [
            {"id": "read_a", "role": "reader", "title": "读取 A", "instructions": "读取 A 并总结", "depends_on": [], "weight": 40},
            {"id": "read_b", "role": "reader", "title": "读取 B", "instructions": "读取 B 并总结", "depends_on": [], "weight": 40},
            {"id": "review", "role": "reviewer", "title": "检查汇总", "instructions": "只读检查两个摘要", "depends_on": ["read_a", "read_b"], "weight": 20},
        ],
    }

    def handler(request: httpx.Request):
        assert request.headers["authorization"] == "Bearer secret-test-key"
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        assert body["thinking"] == {"type": "disabled"}
        assert "reasoning_effort" not in body
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": json.dumps(plan_json)}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            },
        )

    config = settings()
    client = DeepSeekClient(config, transport=httpx.MockTransport(handler))
    plan, result = Planner(client, config).create_plan("分析两个文件")
    assert plan.mode == "swarm"
    assert len(plan.nodes) == 3
    assert result.usage.prompt_tokens == 100


def test_planner_rejects_cycle():
    plan_json = {
        "mode": "swarm",
        "goal": "错误计划",
        "nodes": [
            {"id": "a", "role": "reader", "title": "读取 A", "instructions": "读取 A", "depends_on": ["b"], "weight": 40},
            {"id": "b", "role": "reader", "title": "读取 B", "instructions": "读取 B", "depends_on": ["a"], "weight": 40},
            {"id": "review", "role": "reviewer", "title": "检查", "instructions": "检查结果", "depends_on": ["a"], "weight": 20},
        ],
    }

    def handler(_: httpx.Request):
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(plan_json)}}]})

    config = settings()
    planner = Planner(DeepSeekClient(config, transport=httpx.MockTransport(handler)), config)
    with pytest.raises(DeepSeekError, match="不符合约定"):
        planner.create_plan("制造循环")


def test_planner_rejects_reviewer_that_misses_terminal_worker():
    plan_json = {
        "mode": "swarm",
        "goal": "生成两个独立结果",
        "acceptance_criteria": ["两个结果都完成"],
        "nodes": [
            {"id": "a", "role": "reader", "title": "结果 A", "instructions": "生成 A", "depends_on": [], "weight": 40},
            {"id": "b", "role": "reader", "title": "结果 B", "instructions": "生成 B", "depends_on": [], "weight": 40},
            {"id": "review", "role": "reviewer", "title": "检查", "instructions": "检查结果", "depends_on": ["a"], "weight": 20},
        ],
    }

    def handler(_: httpx.Request):
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(plan_json)}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    config = settings()
    planner = Planner(DeepSeekClient(config, transport=httpx.MockTransport(handler)), config)
    with pytest.raises(DeepSeekError, match="不符合约定"):
        planner.create_plan("生成两个结果")


def test_single_mode_allows_sequential_worker_nodes():
    plan = {
        "mode": "single",
        "goal": "先检索再生成文档",
        "nodes": [
            {"id": "research", "role": "researcher", "title": "检索新闻", "instructions": "检索十条新闻", "depends_on": [], "weight": 40},
            {"id": "write", "role": "document", "title": "生成文档", "instructions": "生成 Markdown 文件", "depends_on": ["research"], "weight": 40},
            {"id": "review", "role": "reviewer", "title": "检查文档", "instructions": "检查文件与来源", "depends_on": ["write"], "weight": 20},
        ],
    }
    from app.agent.planner import TaskPlan

    parsed = TaskPlan.model_validate(plan)
    assert parsed.mode == "single"
    assert len(parsed.nodes) == 3


def test_plan_supports_eight_workers_plus_reviewer():
    from app.agent.planner import TaskPlan

    workers = [
        {
            "id": f"worker_{index}",
            "role": "reader",
            "title": f"处理文件 {index}",
            "instructions": f"独立处理第 {index} 份文件",
            "depends_on": [],
            "weight": 10,
        }
        for index in range(1, 9)
    ]
    plan = TaskPlan.model_validate(
        {
            "mode": "swarm",
            "goal": "并行处理八份文件",
            "nodes": workers
            + [
                {
                    "id": "review",
                    "role": "reviewer",
                    "title": "检查结果",
                    "instructions": "检查全部八份结果",
                    "depends_on": [item["id"] for item in workers],
                    "weight": 20,
                }
            ],
        }
    )
    assert len(plan.nodes) == 9


def test_excel_office_plan_normalizes_coder_to_data_analyst():
    plan = TaskPlan.model_validate(
        {
            "mode": "single",
            "goal": "生成预算表",
            "nodes": [
                {
                    "id": "work",
                    "role": "coder",
                    "title": "制作工作簿",
                    "instructions": "生成真实 XLSX",
                    "depends_on": [],
                    "weight": 80,
                },
                {
                    "id": "review",
                    "role": "reviewer",
                    "title": "检查结果",
                    "instructions": "检查公式与版式",
                    "depends_on": ["work"],
                    "weight": 20,
                },
            ],
        }
    )
    Planner._normalize_office_roles("制作 Excel 季度预算工作簿", plan)
    assert plan.nodes[0].role == "data_analyst"


def test_explicit_excel_code_request_keeps_coder_role():
    plan = TaskPlan.model_validate(
        {
            "mode": "single",
            "goal": "开发导出程序",
            "nodes": [
                {
                    "id": "work",
                    "role": "coder",
                    "title": "开发程序",
                    "instructions": "编写 Python 导出 XLSX",
                    "depends_on": [],
                    "weight": 80,
                },
                {
                    "id": "review",
                    "role": "reviewer",
                    "title": "检查结果",
                    "instructions": "检查程序",
                    "depends_on": ["work"],
                    "weight": 20,
                },
            ],
        }
    )
    Planner._normalize_office_roles("编写 Python 程序导出 Excel", plan)
    assert plan.nodes[0].role == "coder"


def test_client_redacts_auth_error():
    def handler(_: httpx.Request):
        return httpx.Response(401, json={"error": {"message": "secret-test-key"}})

    config = settings()
    client = DeepSeekClient(config, transport=httpx.MockTransport(handler))
    with pytest.raises(DeepSeekError) as caught:
        client.chat(model="deepseek-v4-pro", messages=[], thinking=False)
    assert "secret-test-key" not in str(caught.value)


def test_client_sends_official_thinking_fields():
    def handler(request: httpx.Request):
        body = json.loads(request.content)
        assert body["model"] == "deepseek-v4-flash"
        assert body["thinking"] == {"type": "enabled"}
        assert body["reasoning_effort"] == "high"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )

    config = settings()
    client = DeepSeekClient(config, transport=httpx.MockTransport(handler))
    client.chat(model="deepseek-v4-flash", messages=[{"role": "user", "content": "test"}], thinking=True)
