from __future__ import annotations

import json
import os
from dataclasses import asdict

from .indexer import IndexRequest


QUEUE_NAME = "anime-indexing"


def _redis():
    import redis

    return redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)


def enqueue(request: IndexRequest) -> None:
    _redis().rpush(QUEUE_NAME, json.dumps({**asdict(request), "source": str(request.source)}))


def dequeue(timeout: int = 5) -> IndexRequest | None:
    item = _redis().blpop(QUEUE_NAME, timeout=timeout)
    if not item:
        return None
    payload = json.loads(item[1])
    from pathlib import Path

    return IndexRequest(**{**payload, "source": Path(payload["source"])})
