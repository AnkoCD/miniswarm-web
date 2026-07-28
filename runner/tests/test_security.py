import hashlib
import hmac
import json
import time
from uuid import uuid4

from fastapi.testclient import TestClient

from runner_app.main import app


def signed_headers(body: bytes, timestamp: int | None = None):
    value = str(timestamp or int(time.time()))
    signature = hmac.new(
        b"test-runner-secret-that-is-long-enough",
        value.encode() + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    return {"X-Runner-Timestamp": value, "X-Runner-Signature": signature, "Content-Type": "application/json"}


def test_runner_rejects_unsigned_request():
    with TestClient(app) as client:
        assert client.post("/v1/tools/execute", json={}).status_code == 401


def test_runner_rejects_expired_signature():
    payload = {
        "request_id": str(uuid4()), "user_id": str(uuid4()), "task_id": str(uuid4()),
        "tool": "list_files", "arguments": {"path": "."},
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    with TestClient(app) as client:
        response = client.post("/v1/tools/execute", content=body, headers=signed_headers(body, int(time.time()) - 120))
    assert response.status_code == 401

