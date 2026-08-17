# Tests for top-level orchestration behavior that spans the wrapper and its
# collaborators. Fakes keep smoke and shutdown assertions hardware/network free.

import threading
from types import SimpleNamespace

from deepwork.blocking.hosts_blocker import DryRunBlocker
from deepwork.config import load_config
from deepwork.state import Mode, SessionState
from main import (
    build_app_objects,
    parse_args,
    run_mode,
    run_smoke,
    shutdown_runtime,
)


def test_browser_opening_is_explicitly_opt_in_from_the_cli():
    """Direct runs stay quiet while the launcher can request one browser tab."""

    assert parse_args([]).open_browser is False
    assert parse_args(["--open-browser"]).open_browser is True


class FakeSpeech:
    def __init__(self):
        self.spoken = []
        self.waited = False

    def say(self, text):
        self.spoken.append(text)

    def wait_idle(self, timeout=None):
        self.waited = True


class FakeState:
    def __init__(self):
        self.last_verdict = None

    def start_session(self, topic):
        self.topic = topic


class FakeAnalyzer:
    pass


class FakeScheduler:
    def __init__(self, speech):
        self.state = FakeState()
        self.analyzer = FakeAnalyzer()
        self.speech = speech

    def _monitor_tick(self):
        # The real scheduler now owns the one-and-only verdict utterance.
        self.state.last_verdict = {
            "productive": True,
            "reason": "Fresh progress is visible.",
        }
        self.speech.say("Fresh progress is visible.")


def test_smoke_cycle_does_not_duplicate_scheduler_speech():
    speech = FakeSpeech()
    run_smoke(FakeScheduler(speech), speech)
    assert speech.spoken == ["Fresh progress is visible."]
    assert speech.waited


def test_ui_mode_forwards_configured_port_and_browser_opt_in():
    """The wrapper passes config and CLI intent to the server abstraction."""

    events = []
    scheduler = FakeScheduler(FakeSpeech())
    scheduler.start = lambda: events.append("scheduler")
    flask_app = object()

    run_mode(
        SimpleNamespace(smoke=False, open_browser=True),
        SimpleNamespace(ui_port=8123),
        scheduler,
        flask_app,
        scheduler.speech,
        server_runner=lambda app, port, **kwargs: events.append(
            ("server", app, port, kwargs)
        ),
    )

    assert events == [
        "scheduler",
        ("server", flask_app, 8123, {"open_browser": True}),
    ]


def test_smoke_mode_ignores_browser_opt_in_and_never_starts_server():
    """Combining --smoke and --open-browser retains the no-server contract."""

    speech = FakeSpeech()
    scheduler = FakeScheduler(speech)

    run_mode(
        SimpleNamespace(smoke=True, open_browser=True),
        SimpleNamespace(ui_port=8123),
        scheduler,
        object(),
        speech,
        server_runner=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("smoke must not start the dashboard server")
        ),
    )

    assert scheduler.state.last_verdict["productive"] is True
    assert speech.waited is True


def test_shutdown_serializes_final_hosts_clear_after_inflight_apply():
    """The final cleanup write must land after any older policy publication."""

    class BlockingBlocker:
        def __init__(self):
            self.operations = []
            self.apply_started = threading.Event()
            self.release_apply = threading.Event()

        def apply(self, domains):
            self.apply_started.set()
            assert self.release_apply.wait(timeout=2)
            self.operations.append(("apply", tuple(domains)))

        def clear(self):
            self.operations.append(("clear", ()))

    class StoppableScheduler:
        def __init__(self):
            self.stopped = threading.Event()
            self.messages = object()

        def stop(self):
            self.stopped.set()

    class RecordingStore:
        def __init__(self):
            self.saved = None
            self.events = []

        def append_session_event(self, event):
            self.events.append(event)

        def save_state(self, data):
            self.saved = data

    class StoppableSpeech:
        def __init__(self):
            self.stopped = False

        def stop(self):
            self.stopped = True

    state = SessionState()
    state.start_session("write")
    access, reason = state.start_goal_access(
        "check the source",
        ["twitter"],
        None,
    )
    assert access is not None and reason == ""
    blocker = BlockingBlocker()
    scheduler = StoppableScheduler()
    store = RecordingStore()
    speech = StoppableSpeech()
    older_writer = threading.Thread(
        target=state.reconcile_enforcement,
        args=(blocker,),
    )
    cleanup = threading.Thread(
        target=shutdown_runtime,
        args=(scheduler, state, blocker, store, speech),
    )

    older_writer.start()
    assert blocker.apply_started.wait(timeout=2)
    cleanup.start()
    assert scheduler.stopped.wait(timeout=2)
    blocker.release_apply.set()
    older_writer.join(timeout=2)
    cleanup.join(timeout=2)

    assert not older_writer.is_alive() and not cleanup.is_alive()
    assert blocker.operations[-1] == ("clear", ())
    assert state.mode is Mode.OFF
    assert state.enforcement_dirty is False
    assert state.goal_access is None
    assert store.events[-1]["event"] == "goal_access_ended"
    assert store.events[-1]["goal"] == "check the source"
    assert store.events[-1]["reason"] == "shutdown"
    assert store.saved is not None
    assert speech.stopped is True


def test_shutdown_rejects_a_late_session_after_terminal_off_publication():
    """Daemon request threads cannot re-enable policy after final cleanup."""

    class BlockingClearBlocker:
        def __init__(self):
            self.clear_started = threading.Event()
            self.release_clear = threading.Event()
            self.operations = []

        def clear(self):
            self.clear_started.set()
            assert self.release_clear.wait(timeout=2)
            self.operations.append("clear")

        def apply(self, domains):
            self.operations.append("apply")

    class Scheduler:
        def __init__(self):
            self.messages = object()

        def stop(self):
            pass

    class Store:
        def append_session_event(self, event):
            pass

        def save_state(self, data):
            pass

    class Speech:
        def stop(self):
            pass

    state = SessionState()
    state.start_session("before shutdown")
    state.reconcile_enforcement(DryRunBlocker())
    blocker = BlockingClearBlocker()
    errors = []

    cleanup = threading.Thread(
        target=shutdown_runtime,
        args=(Scheduler(), state, blocker, Store(), Speech()),
    )

    def late_session_start():
        try:
            with state.goal_access_lifecycle():
                state.start_session("too late")
        except RuntimeError as exc:
            errors.append(str(exc))

    cleanup.start()
    assert blocker.clear_started.wait(timeout=2)
    late_request = threading.Thread(target=late_session_start)
    late_request.start()
    blocker.release_clear.set()
    cleanup.join(timeout=2)
    late_request.join(timeout=2)

    assert not cleanup.is_alive() and not late_request.is_alive()
    assert errors == ["Application shutdown is already in progress."]
    assert blocker.operations == ["clear"]
    assert state.mode is Mode.OFF
    assert state.topic == "before shutdown"
    assert state.enforcement_dirty is False


def test_object_wiring_keeps_progress_and_agent_watch_models_separate(
        tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = load_config({
        "OPENAI_API_KEY": "test-key",
        "VISION_MODEL": "progress-model",
        "PROGRESS_REASONING_EFFORT": "xhigh",
        "AGENT_VISION_MODEL": "agent-model",
        "AGENT_REASONING_EFFORT": "high",
        "TEXT_MODEL": "text-model",
        "TEXT_REASONING_EFFORT": "medium",
        "TTS_ENGINE": "pyttsx3",
    })

    scheduler, _, (_, _, speech) = build_app_objects(cfg, DryRunBlocker())
    try:
        assert scheduler.analyzer.model == "progress-model"
        assert scheduler.analyzer.reasoning_effort == "xhigh"
        assert scheduler.agent_checker.model == "agent-model"
        assert scheduler.agent_checker.reasoning_effort == "high"
        assert scheduler.messages.model == "text-model"
        assert scheduler.messages.reasoning_effort == "medium"
    finally:
        speech.stop()
