import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings, get_settings


class RunnerError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunnerResult:
    ok: bool
    summary: str
    data: dict[str, Any]


class RunnerClient:
    def __init__(
        self,
        settings: Settings | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._transport = transport

    def execute(
        self,
        *,
        user_id: str,
        task_id: str,
        tool: str,
        arguments: dict[str, Any],
        approval_granted: bool,
        agent_scope: dict[str, Any] | None = None,
    ) -> RunnerResult:
        payload = {
            "request_id": str(uuid.uuid4()),
            "user_id": user_id,
            "task_id": task_id,
            "tool": tool,
            "arguments": arguments,
            "approval_granted": approval_granted,
            "agent_scope": agent_scope,
        }
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        timestamp = str(int(time.time()))
        signature = hmac.new(
            self.settings.runner_shared_secret.encode(),
            timestamp.encode() + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        try:
            with httpx.Client(
                base_url=self.settings.runner_url.rstrip("/"),
                timeout=330,
                transport=self._transport,
            ) as client:
                response = client.post(
                    "/v1/tools/execute",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Runner-Timestamp": timestamp,
                        "X-Runner-Signature": signature,
                    },
                )
            if response.status_code == 422:
                detail = response.json().get("detail", "Runner 拒绝了工具参数")
                raise RunnerError(str(detail))
            response.raise_for_status()
            data = response.json()
            return RunnerResult(
                ok=bool(data["ok"]), summary=str(data["summary"]), data=dict(data.get("data") or {})
            )
        except RunnerError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise RunnerError("Runner 服务不可用或响应无效") from exc

