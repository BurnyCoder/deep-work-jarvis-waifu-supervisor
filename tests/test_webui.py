# Tests for deepwork/webui/app.py using Flask's built-in test client —
# https://flask.palletsprojects.com/en/stable/testing/

from datetime import datetime, timedelta

import pytest

from deepwork.config import CONFIRMATION_PHRASE
from deepwork.state import Mode, SessionState
from deepwork.storage import ResultsStore
from deepwork.webui.app import create_app


class FakeBlocker:
    def __init__(self):
        self.applied, self.cleared = [], 0
    def apply(self, domains):
        self.applied.append(tuple(domains))
    def clear(self):
        self.cleared += 1


class FakeMessages:
    def generate(self, kind, **ctx):
        return f"<{kind}>"


class FakeSpeech:
    def __init__(self):
        self.spoken = []
    def say(self, text):
        self.spoken.append(text)


@pytest.fixture
def ui(tmp_path):
    state = SessionState(project_allowlists={"ml-research": ["twitter"]})
    blocker, speech = FakeBlocker(), FakeSpeech()
    runtime_snapshot = lambda now=None: {
        "running": True,
        "loops": {
            "monitor": {
                "enabled": True,
                "interval_s": 300,
                "phase": "waiting",
                "last_started_at": None,
                "last_finished_at": None,
                "next_due_at": None,
                "next_due_in_s": 120,
                "last_error": None,
                "last_result": None,
            },
        },
    }
    app = create_app(state=state, blocker=blocker, store=ResultsStore(tmp_path),
                     messages=FakeMessages(), speech=speech,
                     runtime_snapshot=runtime_snapshot)
    app.testing = True
    return app.test_client(), state, blocker, speech


def test_index_lists_previous_topics(ui):
    client, state, *_ = ui
    state.previous_topics[:] = ["thesis", "emails"]
    html = client.get("/").get_data(as_text=True)
    assert "thesis" in html and "emails" in html   # datalist options present
    assert "AI-generated" in html                  # required TTS disclosure


def test_start_session_blocks_and_speaks_good_luck(ui):
    client, state, blocker, speech = ui
    resp = client.post("/start", data={"topic": "write thesis"})
    assert resp.status_code in (200, 302)
    assert state.mode is Mode.ON and state.topic == "write thesis"
    assert blocker.applied and "reddit.com" in blocker.applied[-1]
    assert speech.spoken == ["<good_luck>"]        # requirement 4 good-luck


def test_disable_needs_exact_phrase(ui):
    client, state, blocker, _ = ui
    client.post("/start", data={"topic": "t"})
    assert client.post("/disable", data={"phrase": "wrong"}).status_code == 403
    assert state.mode is Mode.ON                   # still enforced
    resp = client.post("/disable", data={"phrase": CONFIRMATION_PHRASE})
    assert resp.status_code in (200, 302)
    assert state.mode is Mode.OFF and blocker.cleared == 1


def test_break_rejected_beyond_allowance(ui):
    client, state, *_ = ui
    client.post("/start", data={"topic": "t"})
    resp = client.post("/break", data={"purpose": "scroll", "minutes": "999",
                                       "kind": "social_media", "allowed_sites": "reddit"})
    assert resp.status_code == 400                 # cap enforced server-side
    assert state.mode is Mode.ON


def test_break_applies_allowance_and_speaks_ack(ui):
    client, state, blocker, speech = ui
    client.post("/start", data={"topic": "t"})
    resp = client.post("/break", data={"purpose": "reddit pause", "minutes": "10",
                                       "kind": "social_media", "allowed_sites": "reddit"})
    assert resp.status_code in (200, 302)
    assert state.mode is Mode.BREAK
    assert "reddit.com" not in blocker.applied[-1] # reddit freed during break
    assert "<break_ack>" in speech.spoken          # TTS acknowledges purpose


def test_status_json_shape(ui):
    client, state, *_ = ui
    client.post("/start", data={"topic": "t"})
    response = client.get("/status")
    data = response.get_json()
    assert data["mode"] == "on" and data["topic"] == "t"
    assert "social_minutes_remaining" in data and "last_verdict" in data
    assert "agentic_mode" in data and "agent_busy" in data
    assert "server_time" in data and "session_elapsed_s" in data
    assert data["monitoring_active"] is True
    assert data["evaluation_history"] == []
    assert data["enforcement"]["blocked_domain_count"] > 0
    assert data["runtime"]["loops"]["monitor"]["next_due_in_s"] == 120
    assert response.headers["Cache-Control"] == "no-store"


def test_status_returns_current_session_history_newest_first(ui):
    client, state, *_ = ui
    client.post("/start", data={"topic": "t"})
    first = datetime(2026, 7, 20, 9, 0, 0)
    state.record_verdict(True, 5, reason="first", observed="document v1",
                         now=first)
    state.record_verdict(False, 5, reason="second", observed="video open",
                         now=first + timedelta(minutes=5))

    data = client.get("/status").get_json()
    assert [item["reason"] for item in data["evaluation_history"]] == [
        "second",
        "first",
    ]
    assert data["last_verdict"]["observed"] == "video open"


def test_status_extends_break_with_countdown_and_allowances(ui):
    client, state, *_ = ui
    client.post("/start", data={"topic": "t"})
    client.post("/break", data={
        "purpose": "call",
        "minutes": "10",
        "kind": "social_media",
        "allowed_sites": "reddit",
        "allowed_apps": "discord",
    })

    br = client.get("/status").get_json()["break"]
    assert 0 < br["remaining_s"] <= 600
    assert br["allowed_sites"] == ["reddit"]
    assert br["allowed_apps"] == ["discord"]


def test_start_with_agentic_checkbox_enables_agentic_mode(ui):
    client, state, *_ = ui
    client.post("/start", data={"topic": "agent run", "agentic": "on"})
    assert state.agentic_mode is True
    # Without the checkbox a later session resets it.
    client.post("/start", data={"topic": "solo work"})
    assert state.agentic_mode is False


def test_agentic_toggle_route_reapplies_blocklist(ui):
    client, state, blocker, _ = ui
    client.post("/start", data={"topic": "t"})
    n = len(blocker.applied)
    resp = client.post("/agentic", data={"enabled": "on"})
    assert resp.status_code in (200, 302)
    assert state.agentic_mode is True
    assert len(blocker.applied) == n + 1           # blocklist re-applied
