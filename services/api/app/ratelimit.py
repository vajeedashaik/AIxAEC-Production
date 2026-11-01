"""Fixed-window rate limiter.

shortcut: counters are per process, so N API processes allow N times the limit; move to Postgres when scaled out.
"""

import threading
import time
from collections import Counter
from typing import Literal

from aec_contracts import ErrorCode

from .errors import ServiceError

clock = time.time
Bucket = Literal["read", "write"]


class RateLimiter:
    def __init__(self, read_per_minute: int, write_per_minute: int) -> None:
        self._limits: dict[Bucket, int] = {"read": read_per_minute, "write": write_per_minute}
        self._lock = threading.Lock()
        self._window = 0
        self._counts: Counter[tuple[str, Bucket]] = Counter()

    def check(self, key: str, bucket: Bucket) -> None:
        now = clock()
        window = int(now // 60)
        with self._lock:
            if window != self._window:  # dropping every counter also keeps memory bounded
                self._window, self._counts = window, Counter()
            self._counts[(key, bucket)] += 1
            count = self._counts[(key, bucket)]
        if count > self._limits[bucket]:
            raise ServiceError(429, ErrorCode.RATE_LIMITED, "Too many requests.",
                               headers={"Retry-After": str(60 - int(now % 60))})
