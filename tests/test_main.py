# Tests for top-level orchestration behavior that spans the wrapper and its
# collaborators. Fakes keep the smoke-cycle assertion hardware/network free.

from deepwork.blocking.hosts_blocker import DryRunBlocker
from deepwork.config import load_config
from main import build_app_objects, run_smoke


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
