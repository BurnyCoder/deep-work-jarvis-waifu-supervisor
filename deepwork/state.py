# Session state machine — the single source of truth for what the app is
# doing right now. Global context: the scheduler threads, the Flask UI and
# the blockers all read/mutate state ONLY through these lock-guarded methods,
# which is the standard way to share state between Python threads:
# https://docs.python.org/3/library/threading.html#lock-objects

# Enum gives named, identity-comparable modes (Mode.ON is Mode.ON):
# https://docs.python.org/3/library/enum.html
import enum
import math
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# Config owns the domain/app tables; state only computes "effective" views.
from deepwork.config import (
    APP_PROCESSES,
    CONFIRMATION_PHRASE,
    SITE_DOMAINS,
    all_blocked_domains,
    expand_www,
)
from deepwork.site_access import (
    normalize_site_keys,
    resolve_work_allowed_sites,
    site_labels,
)


class Mode(enum.Enum):
    # The three operating modes from requirement 5.
    ON = "on"        # blocking + killing + monitoring all active
    OFF = "off"      # everything disabled
    BREAK = "break"  # timed exception window, auto-restores to ON


@dataclass
class BreakInfo:
    # One active break: what for, which kind, until when, what it unlocks.
    purpose: str                                  # user's stated reason
    kind: str                                     # "social_media" | "away"
    start_time: datetime                          # local instant reservation began
    end_time: datetime                            # absolute expiry instant
    requested_minutes: int                        # whole minutes reserved up front
    allowed_sites: tuple[str, ...] = ()           # SITE_DOMAINS keys unblocked
    allowed_apps: tuple[str, ...] = ()            # APP_PROCESSES keys spared


@dataclass(frozen=True)
class BreakStopResult:
    """Immutable accounting record returned after a user stops a break."""

    purpose: str                                  # reason retained for event/TTS
    kind: str                                     # determines allowance accounting
    requested_minutes: int                        # original reservation
    elapsed_seconds: int                          # elapsed time capped at duration
    charged_minutes: int                          # every started minute counts
    refunded_minutes: int                         # social reservation returned


@dataclass
class SessionState:
    # Behavior knobs are injected so tests construct states in one line.
    daily_social_cap_min: int = 120
    # project name -> list of SITE_DOMAINS keys that project may use while ON
    project_allowlists: dict[str, list[str] | tuple[str, ...]] = field(
        default_factory=dict
    )

    # --- runtime fields (not constructor-tuned) ---
    mode: Mode = Mode.OFF
    topic: str = ""
    previous_topics: list[str] = field(default_factory=list)
    active_project: str | None = None
    # One-off website groups chosen for the current task. Unlike project
    # presets, these runtime choices deliberately do not survive a restart.
    task_allowed_sites: tuple[str, ...] = ()
    current_break: BreakInfo | None = None
    # date-iso -> minutes of social break reserved that day; keying by date
    # string makes the midnight rollover automatic and JSON-friendly.
    social_used_by_date: dict[str, int] = field(default_factory=dict)
    productive_streak_min: int = 0                # consecutive productive mins
    last_verdict: dict | None = None              # latest analyzer result
    # Complete in-memory verdict history for the current session. The web UI
    # shows all entries; context_summary() independently slices the newest 5.
    evaluation_history: list[dict] = field(default_factory=list)
    session_start: datetime | None = None         # when ON began (for records)
    session_end: datetime | None = None           # freezes elapsed time after OFF
    # Agentic engineering mode: while an AI coding agent is detected working
    # on another screen, the whole blocklist opens; when it finishes,
    # everything re-blocks (user is "waiting", not slacking).
    agentic_mode: bool = False                    # opted in for this session
    agent_busy: bool = False                      # latest vision verdict

    def __post_init__(self):
        # RLock (reentrant) so a locked method may call another locked method:
        # https://docs.python.org/3/library/threading.html#rlock-objects
        self._lock = threading.RLock()

    # ---------- mode transitions ----------

    def start_session(
        self,
        topic: str,
        now: datetime | None = None,
        *,
        allowed_sites: list[str] | tuple[str, ...] | None = None,
        project: str | None = None,
        agentic: bool = False,
    ) -> None:
        # Requirement 4: topic entered per session, history feeds the dropdown.
        # Validate every option before touching live state, so a forged form
        # value cannot leave a half-started session behind.
        selected_sites = normalize_site_keys(allowed_sites or ())
        project_name = project.strip() if project else None
        resolve_work_allowed_sites(
            selected_sites,
            project_name,
            self.project_allowlists,
        )
        with self._lock:
            self.mode = Mode.ON
            self.session_start = now or datetime.now()
            self.session_end = None
            self.topic = topic
            # A new session is the exact boundary selected for dashboard
            # history; OFF and BREAK deliberately keep the prior entries.
            self.last_verdict = None
            self.evaluation_history.clear()
            self.current_break = None
            self.active_project = project_name
            self.task_allowed_sites = selected_sites
            self.agentic_mode = agentic
            self.agent_busy = False
            # Dedup then prepend → most-recent-first history.
            if topic in self.previous_topics:
                self.previous_topics.remove(topic)
            self.previous_topics.insert(0, topic)
            self.productive_streak_min = 0

    def try_disable(self, phrase: str, now: datetime | None = None) -> bool:
        # Requirement 6: only the EXACT phrase flips everything OFF —
        # comparison is deliberately case- and whitespace-sensitive friction.
        with self._lock:
            if phrase != CONFIRMATION_PHRASE:
                return False
            self.mode = Mode.OFF
            self.current_break = None
            self.session_end = now or datetime.now()
            return True

    # ---------- breaks & allowance ----------

    def social_minutes_remaining(self, now: datetime | None = None) -> int:
        # Cap minus what today already reserved; unknown dates count as 0 used,
        # which IS the midnight rollover (new date → fresh key).
        now = now or datetime.now()
        used = self.social_used_by_date.get(now.date().isoformat(), 0)
        return max(0, self.daily_social_cap_min - used)

    def start_break(self, purpose: str, minutes: int, kind: str,
                    allowed_sites: list[str] | None = None,
                    allowed_apps: list[str] | None = None,
                    now: datetime | None = None) -> tuple[bool, str]:
        """Begin a timed break; returns (ok, reason-if-refused)."""
        now = now or datetime.now()
        with self._lock:
            if self.mode is not Mode.ON:
                return False, "Breaks can only start from an active session."
            if kind == "social_media":
                remaining = self.social_minutes_remaining(now)
                if minutes > remaining:
                    # Requirement 5: hard 2 h/day cap — refuse, don't clamp.
                    return False, (f"Only {remaining} social-media minutes left "
                                   f"today (cap {self.daily_social_cap_min}).")
                # Reserve the minutes up front so parallel requests can't
                # double-spend the allowance.
                key = now.date().isoformat()
                self.social_used_by_date[key] = self.social_used_by_date.get(key, 0) + minutes
            # timedelta arithmetic:
            # https://docs.python.org/3/library/datetime.html#timedelta-objects
            self.current_break = BreakInfo(
                purpose=purpose, kind=kind,
                start_time=now,
                end_time=now + timedelta(minutes=minutes),
                requested_minutes=minutes,
                allowed_sites=tuple(allowed_sites or ()),
                allowed_apps=tuple(allowed_apps or ()),
            )
            self.mode = Mode.BREAK
            return True, ""

    def _restore_after_break(self) -> None:
        """Restore focus-mode fields while the caller holds ``self._lock``."""

        self.current_break = None                  # remove temporary exceptions
        self.mode = Mode.ON                        # resume the active session
        self.productive_streak_min = 0             # restart post-break streak

    def end_break_if_due(self, now: datetime | None = None) -> bool:
        # Called by the enforcer watchdog every few seconds; True = restored.
        now = now or datetime.now()
        with self._lock:
            if self.mode is Mode.BREAK and self.current_break and now >= self.current_break.end_time:
                # Expiry consumes the full up-front reservation, so only the
                # shared mode transition is needed here.
                self._restore_after_break()
                return True
            return False

    def stop_break(self, now: datetime | None = None) -> BreakStopResult | None:
        """Stop the active break and refund unelapsed social-media minutes."""

        current = now or datetime.now()
        with self._lock:
            if self.mode is not Mode.BREAK or self.current_break is None:
                # A stale browser click can race the expiry watchdog; treating
                # it as a no-op keeps the POST idempotent and side-effect free.
                return None

            active_break = self.current_break
            requested_minutes = max(0, active_break.requested_minutes)
            # datetime subtraction yields timedelta; total_seconds preserves
            # sub-second precision before the explicit started-minute rounding:
            # https://docs.python.org/3/library/datetime.html#datetime.timedelta.total_seconds
            raw_elapsed_seconds = max(
                0.0,
                (current - active_break.start_time).total_seconds(),
            )
            capped_elapsed_seconds = min(
                raw_elapsed_seconds,
                requested_minutes * 60,
            )
            # ceil implements the chosen "every started minute counts" rule:
            # https://docs.python.org/3.13/library/math.html#math.ceil
            charged_minutes = min(
                requested_minutes,
                math.ceil(capped_elapsed_seconds / 60),
            )
            refunded_minutes = 0
            if active_break.kind == "social_media":
                refunded_minutes = requested_minutes - charged_minutes
                allowance_date = active_break.start_time.date().isoformat()
                reserved_total = self.social_used_by_date.get(allowance_date, 0)
                # Clamp protects an already-corrupt legacy state value from a
                # refund making the daily usage even more invalid.
                self.social_used_by_date[allowance_date] = max(
                    0,
                    reserved_total - refunded_minutes,
                )

            result = BreakStopResult(
                purpose=active_break.purpose,
                kind=active_break.kind,
                requested_minutes=active_break.requested_minutes,
                elapsed_seconds=math.ceil(capped_elapsed_seconds),
                charged_minutes=charged_minutes,
                refunded_minutes=refunded_minutes,
            )
            self._restore_after_break()
            return result

    # ---------- effective enforcement views ----------

    def _allowed_site_keys(self) -> set[str]:
        # Union of task/preset access and what the current break unlocks.
        allowed = set(self.work_allowed_sites)
        if self.mode is Mode.BREAK and self.current_break:
            allowed |= set(self.current_break.allowed_sites)
        return allowed

    @property
    def work_allowed_sites(self) -> tuple[str, ...]:
        """Return the ordered union of one-off and saved-preset task access."""

        with self._lock:
            return resolve_work_allowed_sites(
                self.task_allowed_sites,
                self.active_project,
                self.project_allowlists,
            )

    def effective_blocklist(self) -> tuple[str, ...]:
        # Full blocklist minus every domain variant of the allowed site keys.
        with self._lock:
            # Agentic mode + agent working = sanctioned waiting time: the
            # ENTIRE blocklist opens (user decision); re-applied full the
            # moment the agent is detected idle.
            if self.mode is Mode.ON and self.agentic_mode and self.agent_busy:
                return ()
            freed = {d for key in self._allowed_site_keys()
                     for d in expand_www(SITE_DOMAINS.get(key, []))}
            return tuple(d for d in all_blocked_domains() if d not in freed)

    def effective_kill_processes(self) -> tuple[str, ...]:
        # Kill list minus processes of apps the current break allows.
        with self._lock:
            spared_keys = set(self.current_break.allowed_apps) \
                if (self.mode is Mode.BREAK and self.current_break) else set()
            spared = {p for key in spared_keys for p in APP_PROCESSES.get(key, [])}
            return tuple(p for procs in APP_PROCESSES.values() for p in procs
                         if p not in spared)

    def set_agentic(self, on: bool) -> None:
        # Enable/disable agentic mode; busy flag resets so unblocking only
        # ever follows a fresh vision verdict, never a stale one.
        with self._lock:
            self.agentic_mode = on
            self.agent_busy = False

    def set_agent_busy(self, busy: bool) -> bool:
        """Record the latest agent-activity verdict; True only on CHANGE so
        the scheduler applies hosts/speech on transitions, not every poll."""
        with self._lock:
            changed = busy != self.agent_busy
            self.agent_busy = busy
            return changed

    def set_project(self, name: str | None) -> None:
        # Requirement 5: a "productive project" may allowlist specific
        # social sites while enforcement stays ON for everything else.
        project_name = name.strip() if name else None
        with self._lock:
            resolve_work_allowed_sites(
                self.task_allowed_sites,
                project_name,
                self.project_allowlists,
            )
            self.active_project = project_name

    # ---------- monitoring hooks ----------

    @property
    def monitoring_active(self) -> bool:
        # Captures/analysis run only during focused work: BREAK of either
        # kind pauses monitoring (nudging someone on a sanctioned break or
        # away from the desk would be noise), OFF disables everything, and
        # agent-busy waiting time is sanctioned too — no nudges while the
        # user's AI agent is still working. Normal monitoring resumes the
        # moment the agent goes idle.
        return self.mode is Mode.ON and not (self.agentic_mode and self.agent_busy)

    @property
    def recent_verdicts(self) -> list[dict]:
        """Return the bounded five-entry context window used by feedback."""

        with self._lock:
            # Return copies so a prompt builder cannot mutate shared state.
            return [dict(item) for item in self.evaluation_history[-5:]]

    def record_verdict(self, productive: bool, minutes: int,
                       observed: str = "", reason: str = "",
                       now: datetime | None = None) -> str | None:
        """Fold one analyzer verdict into the streak; return 'praise'/'nudge'/None.

        Requirement 4: nudge whenever unproductive; praise once per 30
        consecutive productive minutes (streak then restarts so a long
        session earns praise again every 30 min). Every verdict also joins
        the current-session evaluation history for dashboard and TTS grounding.
        """
        with self._lock:
            timestamp = now or datetime.now()
            outcome = None
            if not productive:
                self.productive_streak_min = 0
                outcome = "nudge"
            else:
                self.productive_streak_min += minutes
                if self.productive_streak_min >= 30:
                    self.productive_streak_min = 0
                    outcome = "praise"

            # One canonical entry powers last_verdict, full UI history and the
            # bounded TTS slice, preventing timestamp/content drift.
            entry = {
                "ts": timestamp.isoformat(),
                "productive": productive,
                "reason": reason,
                "observed": observed,
            }
            self.evaluation_history.append(entry)
            self.last_verdict = dict(entry)
            return outcome

    def context_summary(self, now: datetime | None = None) -> str:
        """One multi-line snapshot of the whole session — handed to every TTS
        message prompt so spoken feedback can reference real specifics."""
        now = now or datetime.now()
        with self._lock:
            minutes_in = int((now - self.session_start).total_seconds() // 60) \
                if self.session_start else 0
            lines = [
                f"topic: {self.topic or '(none)'}",
                f"minutes into session: {minutes_in}",
                f"productive streak: {self.productive_streak_min} min",
                f"social allowance left today: {self.social_minutes_remaining(now)} min",
            ]
            if self.active_project:
                lines.append(f"saved project preset: {self.active_project}")
            if self.work_allowed_sites:
                lines.append(
                    "work-required websites allowed: "
                    + ", ".join(self.work_allowed_sites)
                )
            if self.agentic_mode:
                lines.append("agentic mode: on, AI agent currently "
                             + ("working" if self.agent_busy else "idle"))
            if self.current_break:
                lines.append(f"on a {self.current_break.kind} break for: "
                             f"{self.current_break.purpose}")
            recent = self.evaluation_history[-5:]
            if recent:
                lines.append("recent monitor observations (oldest first):")
                lines += [f"  [{datetime.fromisoformat(v['ts']):%H:%M}] "
                          f"{'productive' if v['productive'] else 'NOT productive'}"
                          f" - {v['observed'] or v['reason']}"
                          for v in recent]
            return "\n".join(lines)

    def status_snapshot(self, now: datetime | None = None) -> dict:
        """Return one locked, JSON-safe snapshot for the realtime dashboard."""

        current = now or datetime.now()
        with self._lock:
            # Freeze session duration at disable time; active sessions continue
            # advancing on every poll.
            elapsed_until = self.session_end or current
            elapsed_s = (
                max(0, int((elapsed_until - self.session_start).total_seconds()))
                if self.session_start
                else 0
            )
            if self.mode is Mode.OFF:
                pause_reason = "Enforcement is off."
            elif self.mode is Mode.BREAK:
                pause_reason = "A scheduled break is active."
            elif self.agentic_mode and self.agent_busy:
                pause_reason = "The AI coding agent is working."
            else:
                pause_reason = None

            enforcement_on = self.mode is not Mode.OFF
            blocked_domains = self.effective_blocklist() if enforcement_on else ()
            target_processes = (
                self.effective_kill_processes() if enforcement_on else ()
            )
            br = self.current_break
            work_sites = self.work_allowed_sites
            break_payload = (
                {
                    "purpose": br.purpose,
                    "kind": br.kind,
                    "until": br.end_time.isoformat(),
                    "remaining_s": max(
                        0,
                        int((br.end_time - current).total_seconds()),
                    ),
                    "allowed_sites": list(br.allowed_sites),
                    "allowed_apps": list(br.allowed_apps),
                }
                if br
                else None
            )
            # Reversed copies put the newest item first without exposing the
            # mutable list shared with the scheduler thread.
            history = [dict(item) for item in reversed(self.evaluation_history)]
            return {
                "mode": self.mode.value,
                "topic": self.topic,
                "active_project": self.active_project,
                "work_access": {
                    "project": self.active_project,
                    "selected_sites": list(self.task_allowed_sites),
                    "allowed_sites": list(work_sites),
                    "allowed_site_labels": list(site_labels(work_sites)),
                },
                "session_started_at": (
                    self.session_start.isoformat() if self.session_start else None
                ),
                "session_elapsed_s": elapsed_s,
                "productive_streak_min": self.productive_streak_min,
                "social_minutes_remaining": self.social_minutes_remaining(current),
                "social_minutes_cap": self.daily_social_cap_min,
                "last_verdict": dict(self.last_verdict) if self.last_verdict else None,
                "evaluation_history": history,
                "monitoring_active": self.monitoring_active,
                "monitoring_pause_reason": pause_reason,
                "agentic_mode": self.agentic_mode,
                "agent_busy": self.agent_busy,
                "break": break_payload,
                "enforcement": {
                    "hosts_active": bool(blocked_domains),
                    "blocked_domain_count": len(blocked_domains),
                    "app_killer_active": bool(target_processes),
                    "target_process_count": len(target_processes),
                },
            }

    # ---------- persistence (results/state.json via storage.py) ----------

    def to_dict(self) -> dict:
        # Only what must survive a restart: allowance usage (the 2 h cap must
        # not reset on relaunch) and topic history (UI dropdown). Live mode
        # deliberately resets to OFF for safety on crash/restart.
        with self._lock:
            return {"social_used_by_date": dict(self.social_used_by_date),
                    "previous_topics": list(self.previous_topics)}

    def load_dict(self, data: dict) -> None:
        # Tolerant restore: missing keys default to empty (first run).
        with self._lock:
            self.social_used_by_date = dict(data.get("social_used_by_date", {}))
            self.previous_topics = list(data.get("previous_topics", []))
