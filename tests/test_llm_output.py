# Returned-output integration checks use generated images and fake SDK replies;
# they exercise real logging/state collaborators without hardware, APIs, or speech.

import json
import logging
from types import SimpleNamespace

import pytest
from PIL import Image

from deepwork.feedback.goal_access import InlineGoalAccessFeedback, queue_transition_feedback
from deepwork.feedback.messages import MessageGenerator
from deepwork.llm_output import record_response
from deepwork.logging_setup import setup_logging
from deepwork.monitoring.analyzer import AgentActivityChecker, ProductivityAnalyzer
from deepwork.scheduler import Scheduler
from deepwork.state import SessionState
from deepwork.storage import ResultsStore


def refusal_client():
    """Return one deterministic refusal from either Responses SDK entrypoint."""
    # This mirrors the documented refusal variant, not a successful verdict:
    # https://developers.openai.com/api/docs/guides/structured-outputs
    payload = {"status": "completed", "output": [
        {"type": "message", "content": [{"type": "refusal", "refusal": "Unavailable."}]},
    ]}
    response = SimpleNamespace(output_parsed=None, output_text="",
                               model_dump=lambda **kwargs: payload)
    return SimpleNamespace(responses=SimpleNamespace(
        parse=lambda **kwargs: response, create=lambda **kwargs: response,
    ))


def test_complete_response_reaches_file_and_terminal(tmp_path, capsys, monkeypatch):
    """Both configured destinations receive the complete Unicode refusal text."""
    root = logging.getLogger()
    # Isolate root logging so this test closes only the handlers it installs.
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(root, "level", root.level)
    refusal = "Complete evidence — café. " * 500
    payload = {"output": [{"type": "refusal", "refusal": refusal}]}
    response = SimpleNamespace(model_dump=lambda **kwargs: payload)
    try:
        path = setup_logging(tmp_path / "logs")
        record_response(response, logger=logging.getLogger("deepwork.test.output"),
                        store=ResultsStore(tmp_path / "results"), kind="vision", request={})
        expected = json.dumps(payload, ensure_ascii=False)
        assert expected in path.read_text(encoding="utf-8")
        assert expected in capsys.readouterr().err
    finally:
        for handler in root.handlers:
            handler.close()  # Release the temporary log before fixture cleanup.


@pytest.mark.parametrize("status", ["incomplete", "failed", "in_progress", "queued", "cancelled"])
def test_explicit_non_completed_status_is_persisted_then_rejected(tmp_path, caplog, status):
    """All workloads share the completed-status gate after evidence recording."""
    payload = {"status": status, "output": []}
    response = SimpleNamespace(model_dump=lambda **kwargs: payload)
    with caplog.at_level(logging.INFO), pytest.raises(ValueError, match=status):
        record_response(response, logger=logging.getLogger(__name__),
                        store=ResultsStore(tmp_path), kind="vision", request={})
    saved = json.loads(next((tmp_path / "llm").glob("*_vision.json")).read_text())
    assert saved["response"] == payload
    assert json.dumps(payload) in caplog.text


@pytest.mark.parametrize("workload", ["vision", "agent_watch"])
def test_refusal_cannot_publish_a_verdict_or_agent_transition(tmp_path, workload):
    """Exercise real tick boundaries with an unusable returned model response."""
    state = SessionState()
    state.start_session("test", agentic=True)
    store, client, spoken = ResultsStore(tmp_path), refusal_client(), []
    scheduler = Scheduler(
        state=state, blocker=SimpleNamespace(), store=store,
        analyzer=ProductivityAnalyzer(client, "fake", store),
        agent_checker=AgentActivityChecker(client, "fake", store),
        messages=MessageGenerator(client, "fake", store),
        speech=SimpleNamespace(say=spoken.append),
        capture_interval_s=300, kill_interval_s=3,
        capture_fn=lambda: Image.new("RGB", (2, 2), "white"),
        kill_fn=lambda names: [],
    )
    tick = scheduler._monitor_tick if workload == "vision" else scheduler._agent_watch_tick
    with pytest.raises(ValueError, match="no usable output"):
        tick()
    assert state.evaluation_history == []
    assert state.agent_busy is False
    assert spoken == []
    assert list((tmp_path / "sessions").glob("*.jsonl")) == []
    assert len(list((tmp_path / "llm").glob(f"*_{workload}.json"))) == 1


def test_refused_transition_message_does_not_enqueue_speech(tmp_path):
    """The production delivery boundary catches unusable feedback without speech."""
    state, spoken = SessionState(), []
    queue_transition_feedback(state, "good_luck", waits_for_policy=False, topic="test")
    state.release_goal_access_feedback()
    delivery = InlineGoalAccessFeedback(
        state, MessageGenerator(refusal_client(), "fake", ResultsStore(tmp_path)),
        SimpleNamespace(say=spoken.append),
    )
    delivery.wake()
    assert spoken == []
    assert len(list((tmp_path / "llm").glob("*_message.json"))) == 1
