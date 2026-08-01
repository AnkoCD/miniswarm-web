import json
from threading import Lock

import httpx

from app.core.config import Settings
from app.mini_tot import MiniTotGateway, normalize_reasoning_effort, normalize_reasoning_mode


def settings(**overrides) -> Settings:
    values = {
        "app_env": "test",
        "jwt_secret": "test-secret-that-is-long-enough",
        "deepseek_api_key": "secret-test-key",
        "max_reasoning_parallel_calls": 2,
        "max_reasoning_calls_fast": 2,
        "minitot_max_retries": 0,
    }
    values.update(overrides)
    return Settings(**values)


def response(content: str, *, prompt_tokens: int = 10, completion_tokens: int = 2):
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "prompt_tokens_details": {"cached_tokens": 1},
            },
        },
    )


def test_direct_mode_is_single_call_and_preserves_tools():
    requests = []

    def handler(request: httpx.Request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "done",
                        "reasoning_content": "must stay private",
                    },
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            },
        )

    gateway = MiniTotGateway(settings(), transport=httpx.MockTransport(handler))
    result = gateway.chat(
        model="deepseek-v4-flash",
        messages=[{"role": "user", "content": "do it"}],
        reasoning_mode="direct",
        reasoning_effort="fast",
        tools=[{"type": "function", "function": {"name": "write_file"}}],
    )

    assert result.message["content"] == "done"
    assert "reasoning_content" not in result.message
    assert len(requests) == 1
    assert requests[0]["tools"][0]["function"]["name"] == "write_file"
    assert requests[0]["thinking"] == {"type": "disabled"}


def test_critical_reasoning_is_bounded_and_only_final_call_gets_tools():
    requests = []
    lock = Lock()

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        with lock:
            requests.append(body)
        if body.get("tools"):
            assert any(
                item.get("role") == "system" and "MiniTot" in item.get("content", "")
                for item in body["messages"]
            )
            return response("final", prompt_tokens=20, completion_tokens=4)
        return response(json.dumps({"analysis": "checked", "score": 8}))

    gateway = MiniTotGateway(settings(), transport=httpx.MockTransport(handler))
    result = gateway.chat(
        model="deepseek-v4-pro",
        messages=[{"role": "user", "content": "analyze then act"}],
        reasoning_mode="critical",
        reasoning_effort="fast",
        reasoning_purpose="worker",
        tools=[{"type": "function", "function": {"name": "write_file"}}],
    )

    branch_requests = [item for item in requests if not item.get("tools")]
    final_requests = [item for item in requests if item.get("tools")]
    assert len(branch_requests) == 2
    assert len(final_requests) == 1
    assert all("tools" not in item for item in branch_requests)
    assert result.message["content"] == "final"
    assert result.usage.prompt_tokens == 40
    assert result.usage.completion_tokens == 8
    assert result.usage.cache_hit_tokens == 3


def test_aliases_are_normalized():
    assert normalize_reasoning_mode("no") == "direct"
    assert normalize_reasoning_mode("divergent") == "normal"
    assert normalize_reasoning_effort("low") == "fast"
    assert normalize_reasoning_effort("max") == "high"


def test_auto_fast_stays_single_call():
    calls = []

    def handler(request: httpx.Request):
        calls.append(json.loads(request.content))
        return response("fast")

    result = MiniTotGateway(
        settings(), transport=httpx.MockTransport(handler)
    ).chat(
        model="deepseek-v4-pro",
        messages=[{"role": "user", "content": "plan"}],
        reasoning_mode="auto",
        reasoning_effort="fast",
        reasoning_purpose="planner",
    )
    assert result.message["content"] == "fast"
    assert len(calls) == 1


def test_stream_never_exposes_provider_reasoning_content():
    def handler(_request: httpx.Request):
        stream = (
            'data: {"choices":[{"delta":{"reasoning_content":"secret"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"visible"}}]}\n\n'
            'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":1}}\n\n'
            'data: [DONE]\n\n'
        )
        return httpx.Response(200, content=stream.encode("utf-8"))

    deltas = list(
        MiniTotGateway(settings(), transport=httpx.MockTransport(handler)).stream_chat(
            model="deepseek-v4-flash",
            messages=[{"role": "user", "content": "hello"}],
            reasoning_mode="direct",
            reasoning_effort="fast",
        )
    )
    assert "".join(delta.content for delta in deltas) == "visible"
    assert deltas[-1].usage is not None
    assert deltas[-1].usage.prompt_tokens == 3
