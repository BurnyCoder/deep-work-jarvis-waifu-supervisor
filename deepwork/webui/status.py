# Dashboard payload composition. Global context: domain state and scheduler
# telemetry own their locks; this module merges their JSON-safe snapshots so
# the Flask route remains a thin transport wrapper.

from datetime import datetime
from typing import Callable


def empty_runtime_snapshot(now: datetime | None = None) -> dict:
    """Fallback used by isolated web tests and third-party app factories."""

    # Keep the same public shape even when no Scheduler was injected.
    return {"running": False, "loops": {}}


def build_status_payload(
    state,
    runtime_snapshot: Callable[..., dict],
    now: datetime | None = None,
) -> dict:
    """Merge current session state and loop telemetry into one API payload."""

    current = now or datetime.now()
    payload = state.status_snapshot(now=current)
    # ISO 8601 keeps the response human-readable while numeric countdowns in
    # the nested snapshots avoid browser timezone arithmetic.
    payload["server_time"] = current.isoformat()
    payload["runtime"] = runtime_snapshot(now=current)
    return payload
