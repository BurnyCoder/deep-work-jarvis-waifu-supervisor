# Tests for deepwork/state.py — the thread-safe session state machine that
# every other module consults. Written FIRST (TDD). Time is injected via a
# `now` parameter everywhere so tests never sleep (testing-clock pattern:
# https://docs.pytest.org/en/stable/how-to/monkeypatch.html).

import threading
from datetime import datetime, timedelta

import pytest

from deepwork.config import CONFIRMATION_PHRASE
from deepwork.state import GoalAccessInfo, Mode, SessionState, goal_access_event

T0 = datetime(2026, 7, 7, 9, 0, 0)  # fixed reference instant for all tests


def make_state(**kw):
    # Small factory keeps each test to one readable construction line.
    defaults = dict(daily_social_cap_min=120, project_allowlists={"ml-research": ["twitter"]})
    defaults.update(kw)
    return SessionState(**defaults)


class RecordingBlocker:
    """Retain each atomic hosts policy so race tests can assert final state."""

    def __init__(self):
        self.applied = []
        self.cleared = 0

    def apply(self, domains):
        """Record the exact immutable policy passed while state is locked."""

        self.applied.append(tuple(domains))

    def clear(self):
        """Record OFF reconciliation without performing a real hosts write."""

        self.cleared += 1


class FailOnceBlocker(RecordingBlocker):
    """Model a transient hosts failure before accepting the retry."""

    def __init__(self):
        super().__init__()
        self.attempts = 0

    def apply(self, domains):
        """Fail the first write and record the policy on the second."""

        self.attempts += 1
        if self.attempts == 1:
            raise OSError("hosts file temporarily unavailable")
        super().apply(domains)


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


@pytest.mark.parametrize(
    ("elapsed_seconds", "charged_minutes"),
    [
        (0, 0),                                    # no elapsed time costs nothing
        (1, 1),                                    # every started minute is charged
        (60, 1),                                   # exact minute boundaries stay exact
        (61, 2),
        (600, 10),
        (900, 10),                                 # never charge beyond the reservation
    ],
)
def test_manual_break_stop_refunds_unelapsed_social_minutes(
    elapsed_seconds,
    charged_minutes,
):
    s = make_state()
    s.start_session("x", now=T0)
    s.productive_streak_min = 25
    s.start_break(
        "scroll",
        10,
        "social_media",
        allowed_sites=["reddit"],
        allowed_apps=["discord"],
        now=T0,
    )

    result = s.stop_break(now=T0 + timedelta(seconds=elapsed_seconds))

    assert result is not None
    assert result.requested_minutes == 10
    assert result.elapsed_seconds == min(elapsed_seconds, 600)
    assert result.charged_minutes == charged_minutes
    assert result.refunded_minutes == 10 - charged_minutes
    assert s.social_minutes_remaining(now=T0) == 120 - charged_minutes
    assert s.mode is Mode.ON and s.current_break is None
    assert s.productive_streak_min == 0
    assert s.monitoring_active
    assert "reddit.com" in s.effective_blocklist()
    assert "discord.exe" in s.effective_kill_processes()


def test_manual_away_break_stop_does_not_change_social_allowance():
    s = make_state()
    s.start_session("x", now=T0)
    s.start_break("walk", 10, "away", now=T0)

    result = s.stop_break(now=T0 + timedelta(minutes=2))

    assert result is not None
    assert result.charged_minutes == 2
    assert result.refunded_minutes == 0
    assert s.social_minutes_remaining(now=T0) == 120


def test_manual_break_stop_is_idempotent_and_preserves_task_access():
    s = make_state()
    s.start_session("publish update", now=T0, allowed_sites=["twitter"])
    assert s.stop_break(now=T0) is None
    s.start_break(
        "reddit pause",
        10,
        "social_media",
        allowed_sites=["reddit"],
        now=T0,
    )

    assert s.stop_break(now=T0 + timedelta(seconds=1)) is not None
    assert s.stop_break(now=T0 + timedelta(seconds=2)) is None
    blocked = s.effective_blocklist()
    assert "x.com" not in blocked and "reddit.com" in blocked


def test_automatic_break_expiry_keeps_the_full_social_reservation():
    s = make_state()
    s.start_session("x", now=T0)
    s.start_break("scroll", 10, "social_media", now=T0)

    assert s.end_break_if_due(now=T0 + timedelta(minutes=10))
    assert s.social_minutes_remaining(now=T0) == 110


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


def test_task_sites_are_free_monitored_access_and_do_not_spare_apps():
    s = make_state()
    s.start_session(
        "publish a LinkedIn update",
        now=T0,
        allowed_sites=["linkedin", "twitter"],
    )
    blocked = s.effective_blocklist()
    assert "linkedin.com" not in blocked and "x.com" not in blocked
    assert "reddit.com" in blocked and "youtube.com" in blocked
    assert "discord.exe" in s.effective_kill_processes()
    assert s.social_minutes_remaining(now=T0) == 120
    assert s.monitoring_active


def test_project_preset_and_one_off_task_sites_are_combined():
    s = make_state()
    s.start_session(
        "share research",
        now=T0,
        project="ml-research",
        allowed_sites=["linkedin", "twitter"],
    )
    assert s.work_allowed_sites == ("twitter", "linkedin")
    snapshot = s.status_snapshot(now=T0)
    assert snapshot["work_access"] == {
        "project": "ml-research",
        "selected_sites": ["twitter", "linkedin"],
        "allowed_sites": ["twitter", "linkedin"],
        "allowed_site_labels": ["X / Twitter", "LinkedIn"],
    }


def test_task_access_resets_on_new_session_and_rejects_unknown_input_atomically():
    s = make_state()
    s.start_session("first", now=T0, allowed_sites=["twitter"])
    s.start_session("second", now=T0 + timedelta(minutes=1))
    assert s.work_allowed_sites == ()
    assert "x.com" in s.effective_blocklist()

    with pytest.raises(ValueError, match="Unknown website group"):
        s.start_session(
            "forged",
            now=T0 + timedelta(minutes=2),
            allowed_sites=["unknown"],
        )
    assert s.topic == "second"
    assert s.mode is Mode.ON


def test_task_access_remains_open_during_break_and_after_agent_finishes():
    s = make_state()
    s.start_session(
        "social campaign",
        now=T0,
        allowed_sites=["twitter"],
        agentic=True,
    )
    s.start_break(
        "reddit pause",
        10,
        "social_media",
        allowed_sites=["reddit"],
        now=T0,
    )
    blocked = s.effective_blocklist()
    assert "x.com" not in blocked and "reddit.com" not in blocked

    s.end_break_if_due(now=T0 + timedelta(minutes=10))
    s.set_agent_busy(True)
    assert s.effective_blocklist() == ()
    s.set_agent_busy(False)
    blocked = s.effective_blocklist()
    assert "x.com" not in blocked and "reddit.com" in blocked


def test_goal_access_validates_every_input_before_mutating_state():
    """Invalid temporary-access requests leave the active session unchanged."""

    s = make_state()
    ok, reason = s.start_goal_access(
        "research sources",
        ["twitter"],
        10,
        now=T0,
    )
    assert not ok and "active session" in reason
    assert s.goal_access is None

    s.start_session("write thesis", now=T0)
    invalid_requests = [
        ("   ", ["twitter"], 10),
        ("research sources", [], 10),
        ("research sources", ["unknown"], 10),
        ("research sources", ["twitter"], 0),
        ("research sources", ["twitter"], 241),
        ("research sources", ["twitter"], True),
    ]
    for goal, sites, minutes in invalid_requests:
        ok, reason = s.start_goal_access(goal, sites, minutes, now=T0)
        assert not ok and reason
        assert s.goal_access is None


def test_goal_access_is_free_repeatable_and_only_one_can_be_active():
    """Sequential grants are unlimited, but concurrent grants are rejected."""

    s = make_state()
    s.start_session("publish research", now=T0)
    allowance_before = s.social_minutes_remaining(now=T0)
    kill_targets_before = s.effective_kill_processes()

    ok, reason = s.start_goal_access(
        "collect quotes",
        ["reddit", "twitter", "twitter"],
        15,
        now=T0,
    )

    assert ok and reason == ""
    assert s.goal_access == GoalAccessInfo(
        goal="collect quotes",
        start_time=T0,
        end_time=T0 + timedelta(minutes=15),
        requested_minutes=15,
        allowed_sites=("reddit", "twitter"),
    )
    assert "reddit.com" not in s.effective_blocklist()
    assert "x.com" not in s.effective_blocklist()
    assert s.social_minutes_remaining(now=T0) == allowance_before
    assert s.monitoring_active
    assert s.effective_kill_processes() == kill_targets_before

    original = s.goal_access
    ok, reason = s.start_goal_access(
        "a competing goal",
        ["youtube"],
        5,
        now=T0 + timedelta(minutes=1),
    )
    assert not ok and "already active" in reason
    assert s.goal_access == original

    assert s.stop_goal_access(now=T0 + timedelta(minutes=2)) == original
    assert s.stop_goal_access(now=T0 + timedelta(minutes=2)) is None
    ok, reason = s.start_goal_access(
        "publish the result",
        ["linkedin"],
        None,
        now=T0 + timedelta(minutes=3),
    )
    assert ok and reason == ""
    assert s.goal_access.requested_minutes is None
    assert s.goal_access.end_time is None
    assert "linkedin.com" not in s.effective_blocklist()
    assert s.social_minutes_remaining(now=T0) == allowance_before
    assert s.effective_kill_processes() == kill_targets_before


def test_goal_access_concurrent_starts_publish_exactly_one_grant():
    """The state lock makes two genuinely simultaneous starts all-or-nothing."""

    s = make_state()
    s.start_session("research", now=T0)
    start_barrier = threading.Barrier(3)
    result_lock = threading.Lock()
    results = {}

    def start(goal, site):
        """Wait for both workers, then retain each result under a test lock."""

        start_barrier.wait()
        result = s.start_goal_access(goal, [site], 10, now=T0)
        with result_lock:
            results[goal] = result

    workers = [
        threading.Thread(target=start, args=("goal a", "twitter")),
        threading.Thread(target=start, args=("goal b", "reddit")),
    ]
    for worker in workers:
        worker.start()
    start_barrier.wait()
    for worker in workers:
        worker.join(timeout=2)

    assert not any(worker.is_alive() for worker in workers)
    assert sum(access is not None for access, _ in results.values()) == 1
    assert s.goal_access is not None
    assert results[s.goal_access.goal] == (s.goal_access, "")


def test_break_suspends_goal_sites_but_timer_continues_and_can_expire():
    """A break re-blocks grant-only sites without pausing the grant deadline."""

    s = make_state()
    s.start_session("write thesis", now=T0, allowed_sites=["linkedin"])
    s.start_goal_access(
        "check discussion",
        ["twitter", "linkedin"],
        10,
        now=T0,
    )
    s.start_break("walk", 5, "away", now=T0)

    blocked = s.effective_blocklist()
    assert "x.com" in blocked
    assert "linkedin.com" not in blocked  # permanent task access stays open
    assert s.status_snapshot(now=T0 + timedelta(minutes=4))["goal_access"][
        "suspended"
    ]
    assert s.end_break_if_due(now=T0 + timedelta(minutes=5))
    assert s.goal_access is not None
    assert "x.com" not in s.effective_blocklist()

    # A later break still does not pause the original absolute deadline.
    s.start_break("walk again", 10, "away", now=T0 + timedelta(minutes=5))

    ended = s.end_goal_access_if_due(now=T0 + timedelta(minutes=10))

    assert ended is not None and ended.goal == "check discussion"
    assert s.goal_access is None
    assert s.mode is Mode.BREAK


def test_session_boundaries_clear_goal_access_without_persisting_it():
    """Replacement, Disable, and restart are terminal boundaries for a grant."""

    s = make_state()
    s.start_session("first", now=T0)
    s.start_goal_access("research", ["twitter"], None, now=T0)

    replaced = s.start_session("second", now=T0 + timedelta(minutes=1))

    assert replaced is not None and replaced.goal == "research"
    assert s.goal_access is None
    s.start_goal_access("publish", ["linkedin"], None, now=T0)
    ok, disabled = s.try_disable_with_goal_access(
        "wrong phrase",
        now=T0 + timedelta(minutes=2),
    )
    assert not ok and disabled is None
    assert s.goal_access is not None
    ok, disabled = s.try_disable_with_goal_access(
        CONFIRMATION_PHRASE,
        now=T0 + timedelta(minutes=2),
    )
    assert ok
    assert disabled is not None and disabled.goal == "publish"
    assert s.goal_access is None

    restored = make_state()
    restored.load_dict(s.to_dict())
    assert restored.goal_access is None


def test_goal_access_status_context_and_monitoring_context_are_complete():
    """UI, speech, and vision receive coherent views of the same active grant."""

    s = make_state()
    s.start_session("publish research", now=T0, allowed_sites=["linkedin"])
    s.start_goal_access(
        "fetch exact wording",
        ["twitter"],
        10,
        now=T0 + timedelta(minutes=1),
    )

    payload = s.status_snapshot(now=T0 + timedelta(minutes=4))["goal_access"]
    assert payload == {
        "goal": "fetch exact wording",
        "allowed_sites": ["twitter"],
        "allowed_site_labels": ["X / Twitter"],
        "started_at": (T0 + timedelta(minutes=1)).isoformat(),
        "expires_at": (T0 + timedelta(minutes=11)).isoformat(),
        "requested_minutes": 10,
        "remaining_s": 420,
        "until_session_end": False,
        "suspended": False,
    }
    assert "temporary access goal: fetch exact wording" in s.context_summary(
        now=T0 + timedelta(minutes=4)
    )
    assert "temporary website groups selected: twitter" in s.context_summary(
        now=T0 + timedelta(minutes=4)
    )
    context = s.monitoring_context()
    assert context.session_start == T0
    assert context.topic == "publish research"
    assert context.permanent_sites == ("linkedin",)
    assert context.goal_access_start_time == T0 + timedelta(minutes=1)
    assert context.goal_access_goal == "fetch exact wording"
    assert context.goal_access_sites == ("twitter",)


def test_goal_access_event_is_complete_json_safe_and_canonical():
    """Every producer serializes grant transitions through one pure helper."""

    access = GoalAccessInfo(
        goal="fetch exact wording",
        start_time=T0,
        end_time=T0 + timedelta(minutes=10),
        requested_minutes=10,
        allowed_sites=("twitter",),
    )

    assert goal_access_event(
        "goal_access_ended",
        access,
        ended_at=T0 + timedelta(minutes=7),
        reason="manual",
    ) == {
        "event": "goal_access_ended",
        "goal": "fetch exact wording",
        "allowed_sites": ["twitter"],
        "allowed_site_labels": ["X / Twitter"],
        "started_at": T0.isoformat(),
        "expires_at": (T0 + timedelta(minutes=10)).isoformat(),
        "requested_minutes": 10,
        "until_session_end": False,
        "ended_at": (T0 + timedelta(minutes=7)).isoformat(),
        "reason": "manual",
    }


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
        s.record_verdict(True, minutes=5, observed=f"screen shows doc v{i}",
                         now=T0 + timedelta(minutes=i * 5))
    # The dashboard keeps the complete current-session history while TTS
    # context remains intentionally bounded to its newest five evaluations.
    assert len(s.evaluation_history) == 7
    assert len(s.recent_verdicts) == 5
    assert s.recent_verdicts[-1]["observed"] == "screen shows doc v6"
    assert s.recent_verdicts[0]["observed"] == "screen shows doc v2"
    assert s.evaluation_history[0]["ts"] == T0.isoformat()


def test_new_session_resets_visible_history_but_disable_preserves_last_session():
    s = make_state()
    s.start_session("first", now=T0)
    s.record_verdict(True, minutes=5, reason="made progress", now=T0)
    assert len(s.evaluation_history) == 1

    # OFF is still a useful review state, so the completed session remains
    # visible until the user explicitly starts a new one.
    assert s.try_disable(CONFIRMATION_PHRASE, now=T0 + timedelta(minutes=7))
    assert s.last_verdict["reason"] == "made progress"
    assert len(s.evaluation_history) == 1

    s.start_session("second", now=T0 + timedelta(minutes=10))
    assert s.last_verdict is None
    assert s.evaluation_history == []
    assert s.recent_verdicts == []


def test_status_snapshot_is_consistent_and_reports_live_enforcement():
    s = make_state()
    off = s.status_snapshot(now=T0)
    assert off["mode"] == "off"
    assert off["session_elapsed_s"] == 0
    assert off["monitoring_pause_reason"] == "Enforcement is off."
    assert off["work_access"] == {
        "project": None,
        "selected_sites": [],
        "allowed_sites": [],
        "allowed_site_labels": [],
    }
    assert off["enforcement"] == {
        "hosts_active": False,
        "blocked_domain_count": 0,
        "app_killer_active": False,
        "target_process_count": 0,
        "reconciliation_pending": False,
    }

    s.start_session("thesis", now=T0)
    s.record_verdict(False, minutes=5, reason="stalled",
                     observed="editor unchanged",
                     now=T0 + timedelta(minutes=5))
    on = s.status_snapshot(now=T0 + timedelta(minutes=6))
    assert on["session_started_at"] == T0.isoformat()
    assert on["session_elapsed_s"] == 360
    assert on["monitoring_active"] is True
    assert on["monitoring_pause_reason"] is None
    assert on["social_minutes_cap"] == 120
    assert on["last_verdict"] == on["evaluation_history"][0]
    assert on["enforcement"]["blocked_domain_count"] > 0
    assert on["enforcement"]["target_process_count"] > 0


def test_context_summary_grounds_all_the_facts():
    from datetime import timedelta
    s = make_state()
    s.start_session("write thesis", now=T0, allowed_sites=["linkedin"])
    s.record_verdict(False, minutes=25, observed="Reddit threads on monitor 1")
    ctx = s.context_summary(now=T0 + timedelta(minutes=40))
    assert "write thesis" in ctx                   # topic
    assert "40" in ctx                             # minutes into the session
    assert "120" in ctx                            # allowance remaining
    assert "linkedin" in ctx                       # sanctioned task access
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
    s.start_session("write thesis", now=T0, allowed_sites=["twitter"])
    s.start_break("scroll", 15, "social_media", allowed_sites=["reddit"], now=T0)
    restored = make_state()
    restored.load_dict(s.to_dict())                # JSON-safe dict round trip
    # Allowance usage and topic history survive restarts (spec: cap must not
    # reset when the app restarts); live mode intentionally does not.
    assert restored.social_minutes_remaining(now=T0) == 105
    assert restored.previous_topics == ["write thesis"]
    assert restored.work_allowed_sites == ()       # live access never persists


def test_goal_access_start_returns_exact_published_record():
    """Callers receive the frozen record created inside the state lock."""

    s = make_state()
    s.start_session("research", now=T0)

    access, reason = s.start_goal_access(
        "collect citation",
        ["twitter"],
        10,
        now=T0 + timedelta(minutes=1),
    )

    assert reason == ""
    assert access is s.goal_access
    assert access == GoalAccessInfo(
        goal="collect citation",
        start_time=T0 + timedelta(minutes=1),
        end_time=T0 + timedelta(minutes=11),
        requested_minutes=10,
        allowed_sites=("twitter",),
    )


def test_enforcement_reconciliation_retries_failure_and_reports_pending():
    """A failed hosts write stays dirty until one later atomic retry succeeds."""

    s = make_state()
    blocker = FailOnceBlocker()
    s.start_session("write", now=T0)

    assert s.enforcement_dirty
    assert s.status_snapshot(now=T0)["enforcement"][
        "reconciliation_pending"
    ]
    with pytest.raises(OSError, match="temporarily unavailable"):
        s.reconcile_enforcement(blocker)

    assert s.enforcement_dirty
    assert s.status_snapshot(now=T0)["enforcement"][
        "reconciliation_pending"
    ]
    assert s.reconcile_enforcement(blocker) is True
    assert blocker.applied[-1] == s.effective_blocklist()
    assert not s.enforcement_dirty
    assert not s.status_snapshot(now=T0)["enforcement"][
        "reconciliation_pending"
    ]
    assert s.reconcile_enforcement(blocker) is False
    assert blocker.attempts == 2


def test_reconcile_clears_hosts_when_latest_state_is_off():
    """OFF reconciliation uses the backend clear operation under the lock."""

    s = make_state()
    blocker = RecordingBlocker()
    s.start_session("write", now=T0)
    s.reconcile_enforcement(blocker)
    assert s.try_disable(CONFIRMATION_PHRASE, now=T0 + timedelta(minutes=1))

    assert s.reconcile_enforcement(blocker) is True
    assert blocker.cleared == 1
    assert not s.enforcement_dirty


def test_monitoring_revision_rejects_a_stale_verdict_atomically():
    """A policy transition and verdict publication cannot cross contexts."""

    s = make_state()
    initial_revision = s.monitoring_context().revision
    s.start_session("write", now=T0)
    expected = s.monitoring_context()
    assert expected.revision > initial_revision

    access, reason = s.start_goal_access(
        "check source",
        ["twitter"],
        5,
        now=T0 + timedelta(minutes=1),
    )
    assert access is not None and reason == ""
    assert s.monitoring_context().revision > expected.revision

    accepted, outcome = s.record_verdict_if_context(
        expected,
        productive=False,
        minutes=5,
        reason="stale analysis",
        now=T0 + timedelta(minutes=2),
    )

    assert (accepted, outcome) == (False, None)
    assert s.last_verdict is None
    assert s.evaluation_history == []


def test_concurrent_reconciliations_finish_with_the_latest_state_policy():
    """The state RLock serializes transitions with their hosts-file writes."""

    class BarrierBlocker(RecordingBlocker):
        """Pause the older apply while it holds the state reconciliation lock."""

        def __init__(self):
            super().__init__()
            self.calls = 0
            self.apply_started = threading.Barrier(2)
            self.release_apply = threading.Barrier(2)

        def apply(self, domains):
            self.calls += 1
            if self.calls == 1:
                self.apply_started.wait(timeout=2)
                self.release_apply.wait(timeout=2)
            super().apply(domains)

    s = make_state()
    s.start_session("research", now=T0)
    s.reconcile_enforcement(RecordingBlocker())
    first, _ = s.start_goal_access("old goal", ["twitter"], 10, now=T0)
    assert first is not None
    blocker = BarrierBlocker()
    errors = []
    new_transition_attempted = threading.Event()

    def stop_and_reconcile():
        try:
            s.stop_goal_access(now=T0 + timedelta(minutes=1))
            s.reconcile_enforcement(blocker)
        except BaseException as exc:
            errors.append(exc)

    def start_new_and_reconcile():
        try:
            new_transition_attempted.set()
            access, reason = s.start_goal_access(
                "new goal",
                ["reddit"],
                10,
                now=T0 + timedelta(minutes=2),
            )
            assert access is not None and reason == ""
            s.reconcile_enforcement(blocker)
        except BaseException as exc:
            errors.append(exc)

    older = threading.Thread(target=stop_and_reconcile)
    newer = threading.Thread(target=start_new_and_reconcile)
    older.start()
    blocker.apply_started.wait(timeout=2)
    newer.start()
    assert new_transition_attempted.wait(timeout=1)
    blocker.release_apply.wait(timeout=2)
    older.join(timeout=2)
    newer.join(timeout=2)

    assert not older.is_alive() and not newer.is_alive()
    assert errors == []
    assert blocker.applied[-1] == s.effective_blocklist()
    assert "reddit.com" not in blocker.applied[-1]
    assert "x.com" in blocker.applied[-1]
    assert not s.enforcement_dirty
