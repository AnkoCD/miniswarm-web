from __future__ import annotations

import json

import redis

from app.core.config import get_settings


def task_channel(task_id: str) -> str:
    return f"miniswarm:task:{task_id}"


def publish_task_event(task_id: str, event_type: str, payload: dict) -> bool:
    try:
        client = redis.Redis.from_url(
            get_settings().redis_url,
            socket_connect_timeout=1,
            socket_timeout=1,
            decode_responses=True,
        )
        client.publish(
            task_channel(task_id),
            json.dumps({"type": event_type, **payload}, ensure_ascii=False),
        )
        client.close()
        return True
    except redis.RedisError:
        return False
