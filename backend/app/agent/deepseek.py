from dataclasses import dataclass
import json
from time import perf_counter
from typing import Any, Iterator

import httpx

from app.core.config import Settings, get_settings


SUPPORTED_MODELS = frozenset({"deepseek-v4-pro", "deepseek-v4-flash"})


def resolve_task_model(model_mode: str, role: str, settings: Settings) -> str:
    if model_mode in SUPPORTED_MODELS:
        return model_mode
    if role == "planner":
        return settings.model_orchestrator
    if role == "reviewer":
        return settings.model_reviewer
    return settings.model_worker


class DeepSeekError(RuntimeError):
    """Safe, credential-free model error."""


@dataclass(frozen=True)
class ModelUsage:
    prompt_tokens: int
    completion_tokens: int
    cache_hit_tokens: int
    duration_ms: int


@dataclass(frozen=True)
class ChatResult:
    message: dict[str, Any]
    usage: ModelUsage


@dataclass(frozen=True)
class ChatDelta:
    content: str
    usage: ModelUsage | None = None


class DeepSeekClient:
    def __init__(
        self,
        settings: Settings | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._transport = transport

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        thinking: bool,
        response_format: dict[str, str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        if not self.settings.deepseek_api_key:
            raise DeepSeekError("DeepSeek API Key 尚未配置")
        if model not in SUPPORTED_MODELS:
            raise DeepSeekError("DeepSeek 模型选择无效")
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens or self.settings.planner_max_tokens,
            "thinking": {"type": "enabled" if thinking else "disabled"},
        }
        if thinking:
            payload["reasoning_effort"] = "max"
        if response_format:
            payload["response_format"] = response_format
        if tools:
            payload["tools"] = tools
        started = perf_counter()
        try:
            with httpx.Client(
                base_url=self.settings.deepseek_base_url.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {self.settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.settings.deepseek_timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.post("/chat/completions", json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.TimeoutException as exc:
            raise DeepSeekError("DeepSeek 请求超时") from exc
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code in {401, 403}:
                message = "DeepSeek 凭据无效或无模型权限"
            elif code == 429:
                message = "DeepSeek 请求过于频繁或额度不足"
            elif code >= 500:
                message = "DeepSeek 服务暂时不可用"
            else:
                message = f"DeepSeek 请求失败（HTTP {code}）"
            raise DeepSeekError(message) from exc
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise DeepSeekError("DeepSeek 响应无法解析") from exc
        duration_ms = int((perf_counter() - started) * 1000)
        try:
            message = body["choices"][0]["message"]
            raw_usage = body.get("usage", {})
            details = raw_usage.get("prompt_tokens_details") or {}
            usage = ModelUsage(
                prompt_tokens=int(raw_usage.get("prompt_tokens", 0)),
                completion_tokens=int(raw_usage.get("completion_tokens", 0)),
                cache_hit_tokens=int(details.get("cached_tokens", 0)),
                duration_ms=duration_ms,
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise DeepSeekError("DeepSeek 响应缺少必要字段") from exc
        return ChatResult(message=message, usage=usage)

    def stream_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        thinking: bool,
        max_tokens: int | None = None,
    ) -> Iterator[ChatDelta]:
        if not self.settings.deepseek_api_key:
            raise DeepSeekError("DeepSeek API Key 尚未配置")
        if model not in SUPPORTED_MODELS:
            raise DeepSeekError("DeepSeek 模型选择无效")
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens or self.settings.planner_max_tokens,
            "thinking": {"type": "enabled" if thinking else "disabled"},
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if thinking:
            payload["reasoning_effort"] = "high"
        started = perf_counter()
        final_usage: dict[str, Any] = {}
        try:
            with httpx.Client(
                base_url=self.settings.deepseek_base_url.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {self.settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.settings.deepseek_timeout_seconds,
                transport=self._transport,
            ) as client:
                with client.stream("POST", "/chat/completions", json=payload) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            break
                        try:
                            body = json.loads(raw)
                        except ValueError:
                            continue
                        if body.get("usage"):
                            final_usage = body["usage"]
                        choices = body.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content")
                        # reasoning_content deliberately never leaves the model adapter.
                        if isinstance(content, str) and content:
                            yield ChatDelta(content=content)
        except httpx.TimeoutException as exc:
            raise DeepSeekError("DeepSeek 请求超时") from exc
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code in {401, 403}:
                message = "DeepSeek 凭据无效或无模型权限"
            elif code == 429:
                message = "DeepSeek 请求过于频繁或额度不足"
            elif code >= 500:
                message = "DeepSeek 服务暂时不可用"
            else:
                message = f"DeepSeek 请求失败（HTTP {code}）"
            raise DeepSeekError(message) from exc
        except httpx.HTTPError as exc:
            raise DeepSeekError("DeepSeek 流式响应中断") from exc
        details = final_usage.get("prompt_tokens_details") or {}
        yield ChatDelta(
            content="",
            usage=ModelUsage(
                prompt_tokens=int(final_usage.get("prompt_tokens", 0)),
                completion_tokens=int(final_usage.get("completion_tokens", 0)),
                cache_hit_tokens=int(details.get("cached_tokens", 0)),
                duration_ms=int((perf_counter() - started) * 1000),
            ),
        )
