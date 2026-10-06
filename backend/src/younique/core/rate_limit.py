from __future__ import annotations

import time
from collections import defaultdict

from younique.core.errors import rate_limited

_buckets: dict[str, list[float]] = defaultdict(list)


def reset_buckets() -> None:
    _buckets.clear()


def hit(key: str, *, limit: int, window_s: int = 60) -> tuple[int, int]:
    now = time.monotonic()
    bucket = [stamp for stamp in _buckets[key] if now - stamp < window_s]
    if len(bucket) >= limit:
        retry_after_ms = int((window_s - (now - bucket[0])) * 1000) + 1
        _buckets[key] = bucket
        raise rate_limited(max(retry_after_ms, 1))
    bucket.append(now)
    _buckets[key] = bucket
    remaining = limit - len(bucket)
    reset = int(window_s - (now - bucket[0]))
    return remaining, reset
