"""In-memory sliding-window rate limiting.

Why this exists: the chat endpoint spends real money on every call. Without a
limit, a single script - or one enthusiastic user during the SUS study - can run
up an OpenAI bill with no ceiling. There is also a per-day cap across all users
so the total spend has a hard bound.

Deliberately dependency-free and in-process. That is the right trade for this
project (one backend instance, tens of users), but it has real limits that
belong in the thesis rather than being discovered later:

- Counters live in memory, so a restart clears them.
- With more than one worker process each keeps its own counters, so the
  effective limit multiplies by the worker count. Run a single worker, or move
  the counters to Postgres/Redis before scaling out.

The clock is injectable so the behaviour is unit-tested without sleeping.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Limit:
    """``max_events`` allowed within any ``window_seconds`` period."""

    max_events: int
    window_seconds: int

    def describe_th(self) -> str:
        if self.window_seconds % 86400 == 0:
            unit = f"{self.window_seconds // 86400} วัน"
        elif self.window_seconds % 3600 == 0:
            unit = f"{self.window_seconds // 3600} ชั่วโมง"
        elif self.window_seconds % 60 == 0:
            unit = f"{self.window_seconds // 60} นาที"
        else:
            unit = f"{self.window_seconds} วินาที"
        return f"{self.max_events} ครั้งต่อ {unit}"


class RateLimiter:
    """Sliding-window counter keyed by an arbitrary string.

    ``check`` is read-only; ``hit`` records an event. They are separate so a
    request can be rejected without being counted against the caller twice.
    """

    def __init__(self, *, clock=time.monotonic) -> None:
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, window_seconds: int, now: float) -> deque[float]:
        events = self._events[key]
        cutoff = now - window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if not events:
            # Drop the key once its window has emptied. Keys are per user /
            # per email / per IP, so without this the dict grows for the
            # lifetime of the process - one entry for every address that ever
            # called, never freed. ``hit`` re-creates it on the next event.
            del self._events[key]
        return events

    def tracked_keys(self) -> int:
        """How many keys currently hold at least one event (memory bound)."""
        with self._lock:
            return len(self._events)

    def retry_after(self, key: str, limit: Limit) -> int | None:
        """Seconds until the caller may retry, or ``None`` if allowed now."""
        now = self._clock()
        with self._lock:
            events = self._prune(key, limit.window_seconds, now)
            if len(events) < limit.max_events:
                return None
            if not events:
                # max_events <= 0: the key is closed outright, and there is no
                # recorded event to compute an expiry from. Setting a limit to 0
                # is a legitimate kill switch, so this must not raise.
                return limit.window_seconds
            oldest = events[0]
            return max(1, int(oldest + limit.window_seconds - now) + 1)

    def hit(self, key: str, limit: Limit) -> None:
        """Record one event against ``key``."""
        now = self._clock()
        with self._lock:
            self._prune(key, limit.window_seconds, now)
            self._events[key].append(now)

    def count(self, key: str, limit: Limit) -> int:
        now = self._clock()
        with self._lock:
            return len(self._prune(key, limit.window_seconds, now))

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._events.clear()
            else:
                self._events.pop(key, None)


class RateLimitExceeded(Exception):
    """Raised with the Thai message shown to the user and a retry hint."""

    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after


def enforce(limiter: RateLimiter, key: str, limit: Limit, message: str) -> None:
    """Check ``limit`` for ``key`` and record the event, or raise."""
    wait = limiter.retry_after(key, limit)
    if wait is not None:
        raise RateLimitExceeded(message, wait)
    limiter.hit(key, limit)
