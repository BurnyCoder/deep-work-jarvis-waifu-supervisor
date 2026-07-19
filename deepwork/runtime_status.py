# Thread-safe scheduler telemetry shared by the background loops and web UI.
# Global context: Scheduler is the only writer and Flask is a concurrent
# reader, so this small object hides locking and exposes JSON-safe snapshots.
# Lock guidance: https://docs.python.org/3/library/threading.html#lock-objects

import copy
import math
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Mapping


@dataclass
class _LoopStatus:
    """Mutable internal record for one periodic scheduler loop."""

    interval_s: int
    enabled: bool
    phase: str
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    next_due_at: datetime | None = None
    last_error: str | None = None
    last_result: dict | None = None


def _iso(value: datetime | None) -> str | None:
    """Convert an optional datetime to the JSON-friendly ISO 8601 form."""

    # datetime.isoformat() is the standard reversible representation:
    # https://docs.python.org/3/library/datetime.html#datetime.datetime.isoformat
    return value.isoformat() if value else None


class RuntimeStatus:
    """Record loop cadence and health without exposing Scheduler internals."""

    def __init__(
        self,
        intervals: Mapping[str, int | None],
        now_fn: Callable[[], datetime] | None = None,
    ):
        # A clock callable keeps every countdown deterministic in unit tests.
        self._now = now_fn or datetime.now
        # RLock permits snapshot helpers to be safely composed in the future.
        self._lock = threading.RLock()
        self._running = False
        # A None interval means the optional loop is unavailable, not broken.
        self._loops = {
            name: _LoopStatus(
                interval_s=int(interval or 0),
                enabled=interval is not None,
                phase="stopped" if interval is not None else "disabled",
            )
            for name, interval in intervals.items()
        }

    def start(self, now: datetime | None = None) -> None:
        """Mark enabled loops waiting for their first scheduled execution."""

        current = now or self._now()
        with self._lock:
            self._running = True
            for loop in self._loops.values():
                if not loop.enabled:
                    continue
                loop.phase = "waiting"
                loop.next_due_at = current + timedelta(seconds=loop.interval_s)

    def stop(self) -> None:
        """Mark all enabled loops stopped and remove stale countdowns."""

        with self._lock:
            self._running = False
            for loop in self._loops.values():
                if not loop.enabled:
                    continue
                loop.phase = "stopped"
                loop.next_due_at = None

    def mark_started(self, name: str, now: datetime | None = None) -> None:
        """Record that one scheduled task has begun its blocking work."""

        current = now or self._now()
        with self._lock:
            loop = self._loops[name]
            if not loop.enabled:
                return
            loop.phase = "running"
            loop.last_started_at = current
            loop.next_due_at = None

    def mark_finished(
        self,
        name: str,
        result: dict | None = None,
        now: datetime | None = None,
    ) -> None:
        """Record a successful task result and schedule its next execution."""

        current = now or self._now()
        with self._lock:
            loop = self._loops[name]
            if not loop.enabled:
                return
            loop.phase = "waiting" if self._running else "stopped"
            loop.last_finished_at = current
            loop.next_due_at = (
                current + timedelta(seconds=loop.interval_s)
                if self._running
                else None
            )
            loop.last_error = None
            # Deep-copy caller-owned lists such as killed process names.
            loop.last_result = copy.deepcopy(result)

    def mark_failed(
        self,
        name: str,
        error: BaseException,
        now: datetime | None = None,
    ) -> None:
        """Retain a concise failure while leaving the periodic loop retryable."""

        current = now or self._now()
        with self._lock:
            loop = self._loops[name]
            if not loop.enabled:
                return
            loop.phase = "waiting" if self._running else "stopped"
            loop.last_finished_at = current
            loop.next_due_at = (
                current + timedelta(seconds=loop.interval_s)
                if self._running
                else None
            )
            loop.last_error = f"{type(error).__name__}: {error}"
            loop.last_result = None

    def snapshot(self, now: datetime | None = None) -> dict:
        """Return one complete JSON-safe view of scheduler runtime health."""

        current = now or self._now()
        with self._lock:
            loops = {}
            for name, loop in self._loops.items():
                # ceil() avoids displaying 0 seconds while a fraction remains.
                next_due_in_s = (
                    max(0, math.ceil((loop.next_due_at - current).total_seconds()))
                    if loop.next_due_at
                    else None
                )
                loops[name] = {
                    "enabled": loop.enabled,
                    "interval_s": loop.interval_s,
                    "phase": loop.phase,
                    "last_started_at": _iso(loop.last_started_at),
                    "last_finished_at": _iso(loop.last_finished_at),
                    "next_due_at": _iso(loop.next_due_at),
                    "next_due_in_s": next_due_in_s,
                    "last_error": loop.last_error,
                    "last_result": copy.deepcopy(loop.last_result),
                }
            return {"running": self._running, "loops": loops}
