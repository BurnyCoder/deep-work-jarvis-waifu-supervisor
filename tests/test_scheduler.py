# Tests for deepwork/scheduler.py — the tick methods are called directly so
# tests are deterministic (no sleeping); one test exercises real threads with
# tiny intervals to prove start/stop works.

import threading
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
    # Returns a verdict every call (rolling evaluation behavior) unless None.
    def __init__(self, verdict):
        self.verdict = verdict
        self.captures = []
        self.resets = 0

    def add_capture(self, path, topic, allowed_sites=()):
        self.captures.append((path, topic, tuple(allowed_sites)))
        return self.verdict

    def reset(self):
        self.resets += 1


class FakeAgentChecker:
    # Scriptable sequence of agent_working booleans, one per check() call.
    def __init__(self, sequence):
        self.sequence = list(sequence)
        self.checks = 0

    def check(self, path):
        self.checks += 1
        from deepwork.monitoring.analyzer import AgentActivityVerdict
        return AgentActivityVerdict(agent_working=self.sequence.pop(0),
                                    reason="scripted")


class FakeMessages:
    def __init__(self):
        self.calls = []                            # (kind, kwargs) history

    def generate(self, kind, **ctx):
        self.calls.append((kind, ctx))
        return f"<{kind}>"


class FakeSpeech:
    def __init__(self):
        self.spoken = []

    def say(self, text):
        self.spoken.append(text)


def make_scheduler(tmp_path, verdict=None, state=None, agent_checker=None):
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
        agent_checker=agent_checker,
        agent_check_interval_s=1,
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
    verdict = ProductivityVerdict(productive=False, reason="watching videos",
                                  observed="YouTube fullscreen on monitor 1")
    sched, state, _ = make_scheduler(tmp_path, verdict=verdict)
    state.start_session("thesis", now=T0)
    sched._monitor_tick()
    assert sched.analyzer.captures[0][1] == "thesis"   # topic reaches analyzer
    assert sched.speech.spoken == ["<nudge>"]          # unproductive → nudge
    assert state.last_verdict["reason"] == "watching videos"
    # The nudge prompt receives what was SEEN plus the whole session context.
    kind, kwargs = sched.messages.calls[-1]
    assert kind == "nudge"
    assert kwargs["observed"] == "YouTube fullscreen on monitor 1"
    assert "thesis" in kwargs["session_context"]


def test_monitor_forwards_task_allowed_sites_to_vision_and_message_context(
    tmp_path,
):
    verdict = ProductivityVerdict(
        productive=True,
        reason="The campaign draft is moving.",
        observed="LinkedIn composer shows a task-aligned draft.",
    )
    sched, state, _ = make_scheduler(tmp_path, verdict=verdict)
    state.start_session(
        "publish campaign",
        now=T0,
        allowed_sites=["linkedin", "twitter"],
    )
    sched._monitor_tick()
    assert sched.analyzer.captures[0][2] == ("twitter", "linkedin")
    assert "linkedin" in state.context_summary(now=T0)


def test_productive_encouragement_is_spoken_once_without_second_llm_call(tmp_path):
    reason = "Nice work—you advanced the test suite with three newly passing tests."
    verdict = ProductivityVerdict(
        productive=True,
        reason=reason,
        observed="IDE shows three newly passing tests",
    )
    sched, state, _ = make_scheduler(tmp_path, verdict=verdict)
    state.start_session("thesis", now=T0)
    sched._monitor_tick()
    # The analyzer-authored encouragement is the one canonical utterance for
    # this verdict, avoiding a duplicate message-model call or double praise.
    assert sched.speech.spoken == [reason]
    assert sched.messages.calls == []
    assert state.last_verdict["reason"] == reason


def test_praise_after_thirty_productive_minutes(tmp_path):
    reason = "Great focus—you are deep in code with the tests green."
    verdict = ProductivityVerdict(
        productive=True,
        reason=reason,
        observed="IDE focused, tests green",
    )
    sched, state, _ = make_scheduler(tmp_path, verdict=verdict)
    state.start_session("thesis", now=T0)
    # Rolling windows overlap, so each verdict advances the streak by only the
    # newest five-minute interval—not the full 25-minute context.
    sched.verdict_minutes = 5
    for _ in range(5):
        sched._monitor_tick()
    assert sched.speech.spoken == [reason] * 5
    sched._monitor_tick()
    assert sched.speech.spoken == [reason] * 5 + ["<praise>"]
    assert [kind for kind, _ in sched.messages.calls] == ["praise"]


def test_progress_window_resets_only_for_a_new_session(tmp_path):
    verdict = ProductivityVerdict(productive=True, reason="progress",
                                  observed="document grew")
    sched, state, _ = make_scheduler(tmp_path, verdict=verdict)
    state.start_session("thesis", now=T0)
    sched._monitor_tick()
    sched._monitor_tick()
    assert sched.analyzer.resets == 1              # one reset for first session

    state.start_session("new topic", now=T0 + timedelta(minutes=1))
    sched._monitor_tick()
    assert sched.analyzer.resets == 2              # changed session → fresh window


def test_agent_watch_unblocks_then_reblocks_on_transitions(tmp_path):
    checker = FakeAgentChecker([True, True, False])
    sched, state, _ = make_scheduler(tmp_path, agent_checker=checker)
    state.start_session("agentic coding", now=T0)
    state.set_agentic(True)
    # Tick 1: agent detected busy → transition → everything unblocks + speech.
    sched._agent_watch_tick()
    assert sched.blocker.applied[-1] == ()          # empty blocklist applied
    assert sched.speech.spoken == ["<agent_running>"]
    # Tick 2: still busy → NO new blocker call, NO repeated speech.
    sched._agent_watch_tick()
    assert len(sched.blocker.applied) == 1
    assert sched.speech.spoken == ["<agent_running>"]
    # Tick 3: agent finished → full blocklist restored + agent_done spoken.
    sched._agent_watch_tick()
    assert "reddit.com" in sched.blocker.applied[-1]
    assert sched.speech.spoken == ["<agent_running>", "<agent_done>"]


def test_agent_watch_restores_task_specific_blocklist(tmp_path):
    checker = FakeAgentChecker([True, False])
    sched, state, _ = make_scheduler(tmp_path, agent_checker=checker)
    state.start_session(
        "publish campaign",
        now=T0,
        allowed_sites=["twitter"],
        agentic=True,
    )
    sched._agent_watch_tick()
    assert sched.blocker.applied[-1] == ()
    sched._agent_watch_tick()
    assert "x.com" not in sched.blocker.applied[-1]
    assert "reddit.com" in sched.blocker.applied[-1]


def test_agent_watch_inactive_without_agentic_mode(tmp_path):
    checker = FakeAgentChecker([True])
    sched, state, _ = make_scheduler(tmp_path, agent_checker=checker)
    state.start_session("normal work", now=T0)      # agentic mode NOT enabled
    sched._agent_watch_tick()
    assert checker.checks == 0                      # no capture, no API call


class ObservedLock:
    """Expose lock-attempt timing without weakening the real mutual exclusion."""

    def __init__(self):
        # A normal primitive lock remains the synchronization implementation:
        # https://docs.python.org/3/library/threading.html#lock-objects
        self._lock = threading.Lock()
        self._counter_lock = threading.Lock()
        self.attempts = 0
        self.second_attempted = threading.Event()

    def acquire(self):
        """Signal the second attempt immediately before it blocks on the lock."""
        with self._counter_lock:
            self.attempts += 1
            attempt = self.attempts
        if attempt == 2:
            self.second_attempted.set()
        return self._lock.acquire()

    def release(self):
        """Release the wrapped primitive lock."""
        self._lock.release()

    def locked(self):
        """Expose the wrapped lock state for the exception-release assertion."""
        return self._lock.locked()

    def __enter__(self):
        """Support the context-manager protocol used by Scheduler."""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Always release the lock when capture returns or raises."""
        self.release()


def test_monitor_and_agent_watch_serialize_shared_capture(tmp_path):
    """The two scheduler consumers must never overlap native capture work."""
    first_capture_started = threading.Event()
    counter_lock = threading.Lock()
    active_captures = 0
    max_active_captures = 0
    capture_calls = 0

    checker = FakeAgentChecker([False])
    verdict = ProductivityVerdict(
        productive=True,
        reason="Focused work is visible.",
        observed="IDE open on monitor 1.",
    )
    sched, state, _ = make_scheduler(
        tmp_path,
        verdict=verdict,
        agent_checker=checker,
    )
    observed_lock = ObservedLock()
    sched._capture_lock = observed_lock
    state.start_session("agentic coding", now=T0, agentic=True)

    def blocking_capture():
        """Hold capture one until the other scheduler path requests the lock."""
        nonlocal active_captures, max_active_captures, capture_calls
        with counter_lock:
            capture_calls += 1
            call_number = capture_calls
            active_captures += 1
            max_active_captures = max(max_active_captures, active_captures)
        try:
            if call_number == 1:
                first_capture_started.set()
                assert observed_lock.second_attempted.wait(timeout=2)
            return Image.new("RGB", (8, 8), "green")
        finally:
            with counter_lock:
                active_captures -= 1

    sched.capture_fn = blocking_capture
    results = {}
    thread_errors = []

    def run_tick(name, tick):
        """Return worker results and exceptions to pytest's main thread."""
        try:
            results[name] = tick()
        except BaseException as exc:                 # retain AssertionError too
            thread_errors.append(exc)

    monitor = threading.Thread(
        target=run_tick,
        args=("monitor", sched._monitor_tick),
    )
    agent_watch = threading.Thread(
        target=run_tick,
        args=("agent_watch", sched._agent_watch_tick),
    )
    monitor.start()
    assert first_capture_started.wait(timeout=1)
    agent_watch.start()
    monitor.join(timeout=3)
    agent_watch.join(timeout=3)

    assert not monitor.is_alive() and not agent_watch.is_alive()
    assert thread_errors == []
    assert results["monitor"]["status"] == "productive"
    assert results["agent_watch"]["status"] == "idle"
    assert capture_calls == 2
    assert max_active_captures == 1


def test_capture_exception_releases_lock_for_next_scheduler_path(tmp_path):
    """A recoverable capture error must not deadlock later capture requests."""
    checker = FakeAgentChecker([False])
    sched, state, _ = make_scheduler(tmp_path, agent_checker=checker)
    state.start_session("agentic coding", now=T0, agentic=True)
    capture_calls = 0

    def fail_once_then_capture():
        """Raise once, then return a valid image to prove lock recovery."""
        nonlocal capture_calls
        capture_calls += 1
        if capture_calls == 1:
            raise RuntimeError("camera unavailable")
        return Image.new("RGB", (8, 8), "green")

    sched.capture_fn = fail_once_then_capture
    failed = sched._monitor_tick()

    assert failed == {
        "status": "capture_failed",
        "error": "RuntimeError: camera unavailable",
    }
    assert not sched._capture_lock.locked()

    recovered = sched._agent_watch_tick()

    assert recovered["status"] == "idle"
    assert capture_calls == 2


def test_threads_start_and_stop_cleanly(tmp_path):
    sched, state, kills = make_scheduler(tmp_path)
    state.start_session("t", now=T0)
    sched.start()
    time.sleep(0.15)                               # let loops tick at least once
    sched.stop()                                   # must return promptly
    assert not any(t.is_alive() for t in sched.threads)
