from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimitExceeded(RuntimeError):
    pass


class InMemoryRateLimiter:
    def __init__(self):
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(
        self,
        bucket: str,
        owner_key: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds
        key = (bucket, owner_key)
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                raise RateLimitExceeded(bucket)
            events.append(now)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
