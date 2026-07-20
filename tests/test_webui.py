# Tests for deepwork/webui/app.py using Flask's built-in test client —
# https://flask.palletsprojects.com/en/stable/testing/

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from deepwork.config import CONFIRMATION_PHRASE, SITE_DOMAINS
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


class FailingBreakEndMessages(FakeMessages):
    def generate(self, kind, **ctx):
        if kind == "break_end_ack":
            raise RuntimeError("text service unavailable")
        return super().generate(kind, **ctx)


def make_ui(tmp_path, *, now_fn=None, messages=None):
    """Build the same dependency-injected Flask UI for fixtures and clock tests."""

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
                     messages=messages or FakeMessages(), speech=speech,
                     runtime_snapshot=runtime_snapshot, now_fn=now_fn)
    app.testing = True
    app.config["TEST_RESULTS_ROOT"] = str(tmp_path)
    return app.test_client(), state, blocker, speech


@pytest.fixture
def ui(tmp_path):
    return make_ui(tmp_path)


def test_index_lists_previous_topics(ui):
    client, state, *_ = ui
    state.previous_topics[:] = ["thesis", "emails"]
    html = client.get("/").get_data(as_text=True)
    assert "thesis" in html and "emails" in html   # datalist options present
    assert "AI-generated" in html                  # required TTS disclosure
    assert "ml-research" in html and "X / Twitter" in html


def test_index_uses_status_first_semantic_dashboard(ui):
    client, *_ = ui
    html = client.get("/").get_data(as_text=True)
    assert 'href="/static/dashboard.css"' in html
    assert 'src="/static/dashboard.js"' in html
    assert html.index('id="live-dashboard"') < html.index('id="controls"')
    assert 'id="connection-status"' in html and 'role="status"' in html
    assert 'id="evaluation-history"' in html
    assert 'id="dashboard-announcement"' in html
    assert 'id="project-detail"' in html
    assert 'aria-live="polite"' in html
    # Placeholders are supplemental; every form field also has a real label.
    assert 'for="session-topic"' in html
    assert 'for="break-purpose"' in html
    assert 'for="disable-phrase"' in html
    assert 'id="stop-break-form"' in html
    assert 'action="/break/stop"' in html
    assert "Stop break and resume work" in html
    break_card = html[
        html.index('aria-labelledby="break-heading"'):
        html.index('aria-labelledby="disable-heading"')
    ]
    assert 'id="stop-break-form"' in break_card
    assert "<fieldset" in html and "Websites needed for this task" in html
    assert all(f'value="{site}"' in html for site in SITE_DOMAINS)
    assert "X / Twitter" in html and "Hacker News" in html


def test_dashboard_assets_implement_safe_non_overlapping_live_updates(ui):
    client, *_ = ui
    css = client.get("/static/dashboard.css")
    js = client.get("/static/dashboard.js")
    assert css.status_code == 200 and js.status_code == 200

    script = js.get_data(as_text=True)
    assert 'fetch("/status"' in script
    assert "setTimeout" in script                 # recursive, non-overlap poll
    assert "visibilitychange" in script           # pause while tab is hidden
    assert 'createElement("details")' in script   # expandable evidence
    assert "allowed_sites" in script              # break allowances stay visible
    assert "work_access" in script                # task allowances stay visible
    assert "Last session task access" in script   # OFF state is not misleading
    assert "stop-break-form" in script             # stop control follows live state
    assert ".textContent" in script               # safe LLM text rendering
    assert ".innerHTML" not in script              # no HTML injection sink


def test_start_session_blocks_and_speaks_good_luck(ui):
    client, state, blocker, speech = ui
    resp = client.post("/start", data={"topic": "write thesis"})
    assert resp.status_code in (200, 302)
    assert state.mode is Mode.ON and state.topic == "write thesis"
    assert blocker.applied and "reddit.com" in blocker.applied[-1]
    assert speech.spoken == ["<good_luck>"]        # requirement 4 good-luck


def test_start_session_unblocks_selected_task_sites_only(ui):
    client, state, blocker, _ = ui
    response = client.post(
        "/start",
        data={
            "topic": "publish launch update",
            "allowed_sites": ["twitter", "linkedin"],
        },
    )
    assert response.status_code in (200, 302)
    assert state.work_allowed_sites == ("twitter", "linkedin")
    assert "x.com" not in blocker.applied[-1]
    assert "linkedin.com" not in blocker.applied[-1]
    assert "reddit.com" in blocker.applied[-1]
    assert state.social_minutes_remaining() == 120


def test_start_session_adds_project_preset_to_one_off_sites(ui):
    client, state, blocker, _ = ui
    response = client.post(
        "/start",
        data={
            "topic": "share model results",
            "project": "ml-research",
            "allowed_sites": ["linkedin"],
        },
    )
    assert response.status_code in (200, 302)
    assert state.work_allowed_sites == ("twitter", "linkedin")
    assert "x.com" not in blocker.applied[-1]
    assert "linkedin.com" not in blocker.applied[-1]


def test_start_rejects_forged_site_without_state_or_hosts_side_effects(ui):
    client, state, blocker, speech = ui
    response = client.post(
        "/start",
        data={"topic": "forged", "allowed_sites": ["unknown"]},
    )
    assert response.status_code == 400
    assert state.mode is Mode.OFF and state.topic == ""
    assert blocker.applied == [] and speech.spoken == []


def test_start_event_records_task_access(ui):
    client, *_ = ui
    client.post(
        "/start",
        data={
            "topic": "publish launch update",
            "project": "ml-research",
            "allowed_sites": ["linkedin"],
            "agentic": "on",
        },
    )
    root = client.application.config["TEST_RESULTS_ROOT"]
    event_file = next((Path(root) / "sessions").glob("*.jsonl"))
    event = json.loads(event_file.read_text(encoding="utf-8").splitlines()[-1])
    assert event["selected_sites"] == ["linkedin"]
    assert event["allowed_sites"] == ["twitter", "linkedin"]
    assert event["project"] == "ml-research"
    assert event["agentic"] is True


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


def test_stop_break_restores_focus_refunds_allowance_and_speaks(tmp_path):
    clock = {"now": datetime(2026, 7, 20, 9, 0, 0)}
    client, state, blocker, speech = make_ui(
        tmp_path,
        now_fn=lambda: clock["now"],
    )
    client.post(
        "/start",
        data={"topic": "publish update", "allowed_sites": ["twitter"]},
    )
    client.post(
        "/break",
        data={
            "purpose": "reddit pause",
            "minutes": "10",
            "kind": "social_media",
            "allowed_sites": "reddit",
            "allowed_apps": "discord",
        },
    )
    assert state.social_minutes_remaining(now=clock["now"]) == 110
    clock["now"] += timedelta(seconds=61)

    response = client.post("/break/stop")

    assert response.status_code == 302
    assert state.mode is Mode.ON and state.current_break is None
    assert state.social_minutes_remaining(now=clock["now"]) == 118
    assert "x.com" not in blocker.applied[-1]      # task access remains open
    assert "reddit.com" in blocker.applied[-1]    # break access closes immediately
    assert speech.spoken[-1] == "<break_end_ack>"
    status = client.get("/status").get_json()
    assert status["break"] is None
    assert status["monitoring_active"] is True

    event_file = next((Path(tmp_path) / "sessions").glob("*.jsonl"))
    event = json.loads(event_file.read_text(encoding="utf-8").splitlines()[-1])
    assert event["event"] == "break_stopped"
    assert event["purpose"] == "reddit pause"
    assert event["requested_minutes"] == 10
    assert event["charged_minutes"] == 2
    assert event["refunded_minutes"] == 8


def test_stop_break_without_active_break_is_a_side_effect_free_redirect(ui):
    client, state, blocker, speech = ui
    client.post("/start", data={"topic": "t"})
    applied_count = len(blocker.applied)
    spoken_count = len(speech.spoken)

    response = client.post("/break/stop")

    assert response.status_code == 302
    assert state.mode is Mode.ON
    assert len(blocker.applied) == applied_count
    assert len(speech.spoken) == spoken_count


def test_stop_break_succeeds_even_when_feedback_generation_fails(tmp_path):
    clock = {"now": datetime(2026, 7, 20, 9, 0, 0)}
    client, state, blocker, speech = make_ui(
        tmp_path,
        now_fn=lambda: clock["now"],
        messages=FailingBreakEndMessages(),
    )
    client.post("/start", data={"topic": "t"})
    client.post(
        "/break",
        data={"purpose": "walk", "minutes": "10", "kind": "away"},
    )
    clock["now"] += timedelta(minutes=2)

    response = client.post("/break/stop")

    assert response.status_code == 302
    assert state.mode is Mode.ON
    assert "reddit.com" in blocker.applied[-1]
    assert speech.spoken == ["<good_luck>", "<break_ack>"]


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
    assert data["work_access"] == {
        "project": None,
        "selected_sites": [],
        "allowed_sites": [],
        "allowed_site_labels": [],
    }
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
