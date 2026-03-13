from __future__ import annotations

import os
from dataclasses import dataclass

import redis
from rq import Queue


@dataclass(frozen=True)
class QueueSettings:
    redis_url: str
    queue_name: str


def get_queue_settings() -> QueueSettings:
    """Queue settings.

    - In docker-compose, set ENTERPRISE_REDIS_URL=redis://redis:6379/0
    - Locally, default to redis://localhost:6379/0
    """

    redis_url = os.getenv("ENTERPRISE_REDIS_URL") or os.getenv("REDIS_URL") or "redis://localhost:6379/0"
    queue_name = os.getenv("ENTERPRISE_QUEUE_NAME") or "enterprise"
    return QueueSettings(redis_url=redis_url, queue_name=queue_name)


def get_redis_connection() -> redis.Redis:
    settings = get_queue_settings()
    return redis.from_url(settings.redis_url)


def get_queue() -> Queue:
    settings = get_queue_settings()
    conn = get_redis_connection()
    return Queue(settings.queue_name, connection=conn)
