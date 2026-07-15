"""Request rate limiting — a per-identity sliding window over the HTTP surface.

Protects the API from hammering and runaway cost (above all the paid Creative Chef on a public
deployment). Deliberately dependency-free and in-memory: one process's view. On a single
container that's a real limit; on multi-instance serverless it's per-instance (still bounds
each instance — a durable backend like Redis/Postgres is the documented upgrade for a true
global limit).

Distinct from budget.py: that caps *spend* on LLM calls; this caps *request rate* on the API.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Optional, Tuple


class RateLimiter:
    """A fixed-capacity sliding window per key. Thread-safe.

    `check(key)` returns `(allowed, retry_after_seconds)` and records the hit when allowed.
    `max_requests <= 0` disables the limiter (always allows) — the clean "off" switch.
    """

    def __init__(self, max_requests: int, window_seconds: float = 60.0) -> None:
        self.max = int(max_requests)
        self.window = float(window_seconds)
        self._hits: "dict[str, deque]" = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.max > 0

    def check(self, key: str, now: Optional[float] = None) -> Tuple[bool, float]:
        if self.max <= 0:
            return True, 0.0
        now = time.monotonic() if now is None else now
        cutoff = now - self.window
        with self._lock:
            dq = self._hits.get(key)
            if dq is None:
                dq = self._hits[key] = deque()
            while dq and dq[0] <= cutoff:            # drop timestamps outside the window
                dq.popleft()
            if not dq and key in self._hits:
                # keep memory bounded: forget keys that have gone quiet, then re-add below
                del self._hits[key]
                dq = self._hits[key] = deque()
            if len(dq) >= self.max:
                return False, max(self.window - (now - dq[0]), 0.0)
            dq.append(now)
            return True, 0.0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
