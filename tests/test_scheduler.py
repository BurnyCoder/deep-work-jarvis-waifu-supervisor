# Tests for deepwork/scheduler.py — the tick methods are called directly so
# tests are deterministic (no sleeping); one test exercises real threads with
# tiny intervals to prove start/stop works.

import time
from datetime import datetime, timedelta

from PIL import Image

from deepwork.monitoring.analyzer import ProductivityVerdict
from deepwork.scheduler import Scheduler
from deepwork.state import Mode, SessionState
from deepwork.storage import ResultsStore

T0 = datetime(2026, 7, 7, 9, 0, 0)


class FakeBlocker:
    def __init__(self):
        self.applied = []
        self.cleared = 0

    def apply(self, domains):
        self.applied.append(tuple(domains))

    def clear(self):
        self.cleared += 1


class FakeAnalyzer:
    # Returns a verdict every call (batch size 1 behavior) unless None.
    def __init__(self, verdict):
        self.verdict = verdict
        self.captures = []

    def add_capture(self, path, topic):
        self.captures.append((path, topic))
        return self.verdict


class FakeMessages:
    def generate(self, kind, **ctx):
        return f"<{kind}>"


class FakeSpeech:
    def __init__(self):
        self.spoken = []

    def say(self, text):
        self.spoken.append(text)


def make_scheduler(tmp_path, verdict=None, state=None):
    state = state or SessionState()
    kills = []
    sched = Scheduler(
        state=state,
        blocker=FakeBlocker(),
        store=ResultsStore(tmp_path),
        analyzer=FakeAnalyzer(verdict),
        messages=FakeMessages(),
        speech=FakeSpeech(),
        capture_interval_s=1,
        kill_interval_s=1,
        # capture_fn returns an already-stitched PIL image (hardware-free)
        capture_fn=lambda: Image.new("RGB", (8, 8), "green"),
        kill_fn=lambda names: kills.append(tuple(names)) or [],
    )
    return sched, state, kills


def test_enforcer_tick_kills_only_when_not_off(tmp_path):
    sched, state, kills = make_scheduler(tmp_path)
    sched._enforcer_tick(now=T0)                   # OFF → no sweep
    assert kills == []
    state.start_session("t", now=T0)
    sched._enforcer_tick(now=T0)                   # ON → sweep with kill list
    assert len(kills) == 1 and "discord.exe" in kills[0]


def test_enforcer_tick_restores_after_break_expiry(tmp_path):
    sched, state, _ = make_scheduler(tmp_path)
    state.start_session("t", now=T0)
    state.start_break("stretch", 10, "away", now=T0)
    sched._enforcer_tick(now=T0 + timedelta(minutes=5))
    assert state.mode is Mode.BREAK                # not due yet
    sched._enforcer_tick(now=T0 + timedelta(minutes=10))
    assert state.mode is Mode.ON                   # watchdog restored ON
    # Hosts re-applied with the FULL blocklist (allowances gone).
    assert sched.blocker.applied and "reddit.com" in sched.blocker.applied[-1]


def test_monitor_tick_skips_when_monitoring_inactive(tmp_path):
    sched, state, _ = make_scheduler(tmp_path)
    sched._monitor_tick()                          # OFF → no capture at all
    assert sched.analyzer.captures == []


def test_capture_verdict_nudge_flows_to_speech(tmp_path):
    verdict = ProductivityVerdict(productive=False, reason="watching videos")
    sched, state, _ = make_scheduler(tmp_path, verdict=verdict)
    state.start_session("thesis", now=T0)
    sched._monitor_tick()
    assert sched.analyzer.captures[0][1] == "thesis"   # topic reaches analyzer
    assert sched.speech.spoken == ["<nudge>"]          # unproductive → nudge
    assert state.last_verdict["reason"] == "watching videos"


def test_praise_after_thirty_productive_minutes(tmp_path):
    verdict = ProductivityVerdict(productive=True, reason="deep in code")
    sched, state, _ = make_scheduler(tmp_path, verdict=verdict)
    state.start_session("thesis", now=T0)
    # Each verdict covers batch_size * interval minutes; with the test's
    # verdict_minutes=25 default two productive verdicts cross the 30-min bar.
    sched.verdict_minutes = 25
    sched._monitor_tick()
    assert sched.speech.spoken == []               # 25 min: not yet
    sched._monitor_tick()
    assert sched.speech.spoken == ["<praise>"]     # 50 min: praise once


def test_threads_start_and_stop_cleanly(tmp_path):
    sched, state, kills = make_scheduler(tmp_path)
    state.start_session("t", now=T0)
    sched.start()
    time.sleep(0.15)                               # let loops tick at least once
    sched.stop()                                   # must return promptly
    assert not any(t.is_alive() for t in sched.threads)
