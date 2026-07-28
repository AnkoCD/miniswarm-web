import hashlib
import hmac
import time

from fastapi import Header, HTTPException, Request, status

from runner_app.config import get_settings


async def verify_runner_signature(
    request: Request,
    x_runner_timestamp: str | None = Header(default=None),
    x_runner_signature: str | None = Header(default=None),
) -> None:
    if not x_runner_timestamp or not x_runner_signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少 Runner 签名")
    try:
        timestamp = int(x_runner_timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Runner 时间戳无效") from exc
    if abs(int(time.time()) - timestamp) > 60:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Runner 签名已过期")
    body = await request.body()
    signed = x_runner_timestamp.encode() + b"." + body
    expected = hmac.new(
        get_settings().shared_secret.encode(), signed, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, x_runner_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Runner 签名无效")

