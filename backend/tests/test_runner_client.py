import hashlib
import hmac
import json

import httpx

from app.agent.runner_client import RunnerClient
from app.core.config import Settings


def test_runner_client_signs_exact_body():
    secret = "test-runner-secret-that-is-long-enough"

    def handler(request: httpx.Request):
        timestamp = request.headers["x-runner-timestamp"]
        expected = hmac.new(
            secret.encode(), timestamp.encode() + b"." + request.content, hashlib.sha256
        ).hexdigest()
        assert hmac.compare_digest(expected, request.headers["x-runner-signature"])
        body = json.loads(request.content)
        assert body["tool"] == "list_files"
        return httpx.Response(200, json={"ok": True, "summary": "ok", "data": {"items": []}})

    settings = Settings(
        app_env="test",
        jwt_secret="test-secret-that-is-long-enough",
        runner_shared_secret=secret,
    )
    result = RunnerClient(settings, httpx.MockTransport(handler)).execute(
        user_id="7a8d20ca-49b7-4372-b0fc-b71b07e92211",
        task_id="56a8875d-f426-48e8-82fa-76267abe3f71",
        tool="list_files",
        arguments={"path": "."},
        approval_granted=False,
    )
    assert result.ok

