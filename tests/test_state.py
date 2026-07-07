# Tests for deepwork/state.py — the thread-safe session state machine that
# every other module consults. Written FIRST (TDD). Time is injected via a
# `now` parameter everywhere so tests never sleep (testing-clock pattern:
# https://docs.pytest.org/en/stable/how-to/monkeypatch.html).

from datetime import datetime, timedelta

from deepwork.config import CONFIRMATION_PHRASE
from deepwork.state import Mode, SessionState

T0 = datetime(2026, 7, 7, 9, 0, 0)  # fixed reference instant for all tests


def make_state(**kw):
    # Small factory keeps each test to one readable construction line.
    defaults = dict(daily_social_cap_min=120, project_allowlists={"ml-research": ["twitter"]})
    defaults.update(kw)
    return SessionState(**defaults)


def test_starts_off_then_on_with_topic_history():
    s = make_state()
    assert s.mode is Mode.OFF                     # nothing enforced at boot
    s.start_session("write thesis", now=T0)
    assert s.mode is Mode.ON
    s.start_session("code review", now=T0)
    # Most-recent-first, deduplicated topic history feeds the UI dropdown.
    s.start_session("write thesis", now=T0)
    assert s.previous_topics[0] == "write thesis"
    assert s.previous_topics.count("write thesis") == 1


def test_disable_requires_exact_phrase():
    s = make_state()
    s.start_session("x", now=T0)
    assert not s.try_disable("i give up")          # wrong phrase → still ON
    assert not s.try_disable(CONFIRMATION_PHRASE.lower())  # case matters
    assert s.mode is Mode.ON
    assert s.try_disable(CONFIRMATION_PHRASE)      # exact phrase → OFF
    assert s.mode is Mode.OFF


def test_social_break_draws_down_daily_allowance():
    s = make_state()
    s.start_session("x", now=T0)
    ok, _ = s.start_break("chill on reddit", 30, "social_media",
                          allowed_sites=["reddit"], now=T0)
    assert ok and s.mode is Mode.BREAK
    assert s.social_minutes_remaining(now=T0) == 90   # 120 - 30 reserved
    # A break longer than what's left must be refused with a reason string.
    s.end_break_if_due(now=T0 + timedelta(minutes=31))
    ok, reason = s.start_break("more reddit", 100, "social_media",
                               allowed_sites=["reddit"], now=T0)
    assert not ok and reason


def test_allowance_resets_at_midnight():
    s = make_state()
    s.start_session("x", now=T0)
    s.start_break("scroll", 120, "social_media", allowed_sites=["reddit"], now=T0)
    assert s.social_minutes_remaining(now=T0) == 0
    tomorrow = T0 + timedelta(days=1)             # usage is keyed by date
    assert s.social_minutes_remaining(now=tomorrow) == 120


def test_break_auto_restores_on_expiry():
    s = make_state()
    s.start_session("x", now=T0)
    s.start_break("stretch", 10, "away", now=T0)
    assert s.mode is Mode.BREAK
    assert not s.end_break_if_due(now=T0 + timedelta(minutes=9))   # not yet
    assert s.end_break_if_due(now=T0 + timedelta(minutes=10))      # due now
    assert s.mode is Mode.ON                       # enforcement resumes


def test_effective_blocklist_honours_break_and_project_allowances():
    s = make_state()
    s.start_session("x", now=T0)
    assert "reddit.com" in s.effective_blocklist()
    # During a reddit-only break, reddit domains unblock, everything else stays.
    s.start_break("reddit break", 10, "social_media", allowed_sites=["reddit"], now=T0)
    blocked = s.effective_blocklist()
    assert "reddit.com" not in blocked and "youtube.com" in blocked
    # Project allowlist frees its sites while ON (requirement 5, last option).
    s.end_break_if_due(now=T0 + timedelta(minutes=10))
    s.set_project("ml-research")
    blocked = s.effective_blocklist()
    assert "x.com" not in blocked and "reddit.com" in blocked


def test_effective_kill_list_honours_break_app_allowance():
    s = make_state()
    s.start_session("x", now=T0)
    assert "discord.exe" in s.effective_kill_processes()
    s.start_break("voice call", 15, "social_media",
                  allowed_sites=["discord"], allowed_apps=["discord"], now=T0)
    killed = s.effective_kill_processes()
    assert "discord.exe" not in killed and "steam.exe" in killed


def test_recent_verdicts_window_stores_observed_and_caps_at_five():
    s = make_state()
    s.start_session("thesis", now=T0)
    for i in range(7):                             # 7 verdicts → keep last 5
        s.record_verdict(True, minutes=5, observed=f"screen shows doc v{i}")
    assert len(s.recent_verdicts) == 5
    assert s.recent_verdicts[-1]["observed"] == "screen shows doc v6"
    assert s.recent_verdicts[0]["observed"] == "screen shows doc v2"


def test_context_summary_grounds_all_the_facts():
    from datetime import timedelta
    s = make_state()
    s.start_session("write thesis", now=T0)
    s.record_verdict(False, minutes=25, observed="Reddit threads on monitor 1")
    ctx = s.context_summary(now=T0 + timedelta(minutes=40))
    assert "write thesis" in ctx                   # topic
    assert "40" in ctx                             # minutes into the session
    assert "120" in ctx                            # allowance remaining
    assert "Reddit threads on monitor 1" in ctx    # recent observation window


def test_verdict_streak_praise_and_nudge():
    s = make_state()
    s.start_session("x", now=T0)
    # Unproductive verdict → "nudge" and streak reset.
    assert s.record_verdict(False, minutes=25) == "nudge"
    # 25 productive minutes: no praise yet (threshold is 30).
    assert s.record_verdict(True, minutes=25) is None
    # Crossing 30 consecutive minutes → one "praise", then streak restarts.
    assert s.record_verdict(True, minutes=25) == "praise"
    assert s.record_verdict(True, minutes=25) is None


def test_monitoring_only_active_when_on():
    s = make_state()
    assert not s.monitoring_active                 # OFF → no captures
    s.start_session("x", now=T0)
    assert s.monitoring_active                     # ON → capture loop runs
    s.start_break("walk", 10, "away", now=T0)
    assert not s.monitoring_active                 # breaks pause monitoring


def test_agentic_mode_unblocks_everything_only_while_agent_busy():
    s = make_state()
    s.start_session("agentic coding", now=T0)
    s.set_agentic(True)
    # Agent not (yet) detected busy → everything still blocked.
    assert "reddit.com" in s.effective_blocklist()
    assert s.set_agent_busy(True) is True          # transition reported
    assert s.effective_blocklist() == ()           # user decision: ALL unblocked
    assert s.set_agent_busy(True) is False         # same verdict → no transition
    assert s.set_agent_busy(False) is True         # agent finished → transition
    assert "reddit.com" in s.effective_blocklist() # full blocklist restored


def test_agentic_busy_requires_agentic_mode_and_on():
    s = make_state()
    s.start_session("x", now=T0)
    s.set_agent_busy(True)                         # busy but agentic mode OFF
    assert "reddit.com" in s.effective_blocklist() # → no unblocking


def test_agentic_busy_pauses_productivity_monitoring():
    # Sanctioned downtime: no captures/nudges while the agent works; normal
    # monitoring resumes once the agent goes idle.
    s = make_state()
    s.start_session("x", now=T0)
    s.set_agentic(True)
    assert s.monitoring_active
    s.set_agent_busy(True)
    assert not s.monitoring_active
    s.set_agent_busy(False)
    assert s.monitoring_active


def test_persistence_round_trip():
    s = make_state()
    s.start_session("write thesis", now=T0)
    s.start_break("scroll", 15, "social_media", allowed_sites=["reddit"], now=T0)
    restored = make_state()
    restored.load_dict(s.to_dict())                # JSON-safe dict round trip
    # Allowance usage and topic history survive restarts (spec: cap must not
    # reset when the app restarts); live mode intentionally does not.
    assert restored.social_minutes_remaining(now=T0) == 105
    assert restored.previous_topics == ["write thesis"]
