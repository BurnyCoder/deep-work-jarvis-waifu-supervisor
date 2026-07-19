# Tests for the scheduler's shared runtime telemetry. A mutable injected clock
# makes countdowns and task transitions deterministic without sleeping.

from datetime import datetime, timedelta

from deepwork.runtime_status import RuntimeStatus

T0 = datetime(2026, 7, 20, 9, 0, 0)


def test_runtime_status_tracks_cadence_phases_results_and_disabled_loops():
    clock = [T0]
    runtime = RuntimeStatus(
        {"monitor": 300, "enforcer": 3, "agent_watch": None},
        now_fn=lambda: clock[0],
    )

    runtime.start()
    started = runtime.snapshot()
    assert started["running"] is True
    assert started["loops"]["monitor"]["phase"] == "waiting"
    assert started["loops"]["monitor"]["next_due_in_s"] == 300
    assert started["loops"]["agent_watch"]["phase"] == "disabled"

    clock[0] += timedelta(seconds=300)
    runtime.mark_started("monitor")
    running = runtime.snapshot()
    assert running["loops"]["monitor"]["phase"] == "running"
    assert running["loops"]["monitor"]["next_due_at"] is None

    clock[0] += timedelta(seconds=8)
    runtime.mark_finished("monitor", {"status": "productive"})
    finished = runtime.snapshot()
    monitor = finished["loops"]["monitor"]
    assert monitor["last_finished_at"] == clock[0].isoformat()
    assert monitor["next_due_in_s"] == 300
    assert monitor["last_result"] == {"status": "productive"}
    assert monitor["last_error"] is None

    runtime.stop()
    stopped = runtime.snapshot()
    assert stopped["running"] is False
    assert stopped["loops"]["monitor"]["phase"] == "stopped"
    assert stopped["loops"]["monitor"]["next_due_at"] is None


def test_runtime_status_retains_an_error_until_the_next_success():
    clock = [T0]
    runtime = RuntimeStatus({"monitor": 60}, now_fn=lambda: clock[0])
    runtime.start()
    runtime.mark_started("monitor")
    runtime.mark_failed("monitor", RuntimeError("vision unavailable"))

    failed = runtime.snapshot()["loops"]["monitor"]
    assert failed["phase"] == "waiting"
    assert failed["last_error"] == "RuntimeError: vision unavailable"
    assert failed["next_due_in_s"] == 60

    clock[0] += timedelta(seconds=60)
    runtime.mark_started("monitor")
    runtime.mark_finished("monitor", {"status": "productive"})
    assert runtime.snapshot()["loops"]["monitor"]["last_error"] is None
