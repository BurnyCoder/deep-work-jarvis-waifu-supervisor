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


def test_productive_verdict_reason_is_spoken_each_tick(tmp_path):
    verdict = ProductivityVerdict(productive=True, reason="You advanced the test suite.",
                                  observed="IDE shows three newly passing tests")
    sched, state, _ = make_scheduler(tmp_path, verdict=verdict)
    state.start_session("thesis", now=T0)
    sched._monitor_tick()
    # Ordinary productive ticks use the already-generated, fresh vision reason
    # directly, avoiding a second text-model call.
    assert sched.speech.spoken == ["You advanced the test suite."]
    assert sched.messages.calls == []


def test_praise_after_thirty_productive_minutes(tmp_path):
    verdict = ProductivityVerdict(productive=True, reason="deep in code",
                                  observed="IDE focused, tests green")
    sched, state, _ = make_scheduler(tmp_path, verdict=verdict)
    state.start_session("thesis", now=T0)
    # Rolling windows overlap, so each verdict advances the streak by only the
    # newest five-minute interval—not the full 25-minute context.
    sched.verdict_minutes = 5
    for _ in range(5):
        sched._monitor_tick()
    assert sched.speech.spoken == ["deep in code"] * 5
    sched._monitor_tick()
    assert sched.speech.spoken == ["deep in code"] * 5 + ["<praise>"]


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


def test_threads_start_and_stop_cleanly(tmp_path):
    sched, state, kills = make_scheduler(tmp_path)
    state.start_session("t", now=T0)
    sched.start()
    time.sleep(0.15)                               # let loops tick at least once
    sched.stop()                                   # must return promptly
    assert not any(t.is_alive() for t in sched.threads)
