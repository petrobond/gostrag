from __future__ import annotations

import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """In-memory sliding window limiter (per user)."""

    def __init__(self, limit: int, window_sec: int) -> None:
        self.limit = limit
        self.window_sec = window_sec
        self._events: dict[int, deque[float]] = defaultdict(deque)

    def allow(self, user_id: int) -> bool:
        now = time.time()
        bucket = self._events[user_id]
        while bucket and now - bucket[0] > self.window_sec:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True

    def retry_after(self, user_id: int) -> int:
        bucket = self._events[user_id]
        if not bucket:
            return 0
        return max(1, int(self.window_sec - (time.time() - bucket[0])))
