"""In-memory sliding-window rate limits.

Per API process: enough for one server. With several API replicas, each enforces its own window (move the
counters to the database or Redis then).
"""

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._clock = clock

    def check(self, bucket: str, key: str, limit: int, per_seconds: float) -> None:
        """Count a hit; raise 429 if `key` has made more than `limit` in the last `per_seconds`."""
        now = self._clock()
        with self._lock:
            hits = self._hits[(bucket, key)]
            while hits and hits[0] <= now - per_seconds:
                hits.popleft()
            if len(hits) >= limit:
                retry = int(hits[0] + per_seconds - now) + 1
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    f"too many requests; try again in {retry} seconds",
                    headers={"Retry-After": str(retry)},
                )
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_ip(request: Request, trust_proxy: bool) -> str:
    """The caller's address. Behind the web app's proxy every request comes from it, so with `trust_proxy` the
    first X-Forwarded-For entry is used instead (only for rate limiting; a spoofed header can't grant access)."""
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
