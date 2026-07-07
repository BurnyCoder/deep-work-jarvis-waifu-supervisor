# Session state machine — the single source of truth for what the app is
# doing right now. Global context: the scheduler threads, the Flask UI and
# the blockers all read/mutate state ONLY through these lock-guarded methods,
# which is the standard way to share state between Python threads:
# https://docs.python.org/3/library/threading.html#lock-objects

# Enum gives named, identity-comparable modes (Mode.ON is Mode.ON):
# https://docs.python.org/3/library/enum.html
import enum
import threading
from dataclasses import dataclass, field
from datetime import datetime

# Config owns the domain/app tables; state only computes "effective" views.
from deepwork.config import (
    APP_PROCESSES,
    CONFIRMATION_PHRASE,
    SITE_DOMAINS,
    all_blocked_domains,
    expand_www,
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
    end_time: datetime                            # absolute expiry instant
    allowed_sites: tuple[str, ...] = ()           # SITE_DOMAINS keys unblocked
    allowed_apps: tuple[str, ...] = ()            # APP_PROCESSES keys spared


@dataclass
class SessionState:
    # Behavior knobs are injected so tests construct states in one line.
    daily_social_cap_min: int = 120
    # project name -> list of SITE_DOMAINS keys that project may use while ON
    project_allowlists: dict[str, list[str]] = field(default_factory=dict)

    # --- runtime fields (not constructor-tuned) ---
    mode: Mode = Mode.OFF
    topic: str = ""
    previous_topics: list[str] = field(default_factory=list)
    active_project: str | None = None
    current_break: BreakInfo | None = None
    # date-iso -> minutes of social break reserved that day; keying by date
    # string makes the midnight rollover automatic and JSON-friendly.
    social_used_by_date: dict[str, int] = field(default_factory=dict)
    productive_streak_min: int = 0                # consecutive productive mins
    last_verdict: dict | None = None              # latest analyzer result
    session_start: datetime | None = None         # when ON began (for records)

    def __post_init__(self):
        # RLock (reentrant) so a locked method may call another locked method:
        # https://docs.python.org/3/library/threading.html#rlock-objects
        self._lock = threading.RLock()

    # ---------- mode transitions ----------

    def start_session(self, topic: str, now: datetime | None = None) -> None:
        # Requirement 4: topic entered per session, history feeds the dropdown.
        with self._lock:
            self.mode = Mode.ON
            self.session_start = now or datetime.now()
            self.topic = topic
            # Dedup then prepend → most-recent-first history.
            if topic in self.previous_topics:
                self.previous_topics.remove(topic)
            self.previous_topics.insert(0, topic)
            self.productive_streak_min = 0

    def try_disable(self, phrase: str) -> bool:
        # Requirement 6: only the EXACT phrase flips everything OFF —
        # comparison is deliberately case- and whitespace-sensitive friction.
        with self._lock:
            if phrase != CONFIRMATION_PHRASE:
                return False
            self.mode = Mode.OFF
            self.current_break = None
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
            # timedelta arithmetic: https://docs.python.org/3/library/datetime.html#timedelta-objects
            from datetime import timedelta
            self.current_break = BreakInfo(
                purpose=purpose, kind=kind,
                end_time=now + timedelta(minutes=minutes),
                allowed_sites=tuple(allowed_sites or ()),
                allowed_apps=tuple(allowed_apps or ()),
            )
            self.mode = Mode.BREAK
            return True, ""

    def end_break_if_due(self, now: datetime | None = None) -> bool:
        # Called by the enforcer watchdog every few seconds; True = restored.
        now = now or datetime.now()
        with self._lock:
            if self.mode is Mode.BREAK and self.current_break and now >= self.current_break.end_time:
                self.current_break = None
                self.mode = Mode.ON               # auto-restore (requirement 5)
                self.productive_streak_min = 0    # streak restarts after break
                return True
            return False

    # ---------- effective enforcement views ----------

    def _allowed_site_keys(self) -> set[str]:
        # Union of what the current break and the active project unlock.
        allowed: set[str] = set()
        if self.mode is Mode.BREAK and self.current_break:
            allowed |= set(self.current_break.allowed_sites)
        if self.active_project:
            allowed |= set(self.project_allowlists.get(self.active_project, []))
        return allowed

    def effective_blocklist(self) -> tuple[str, ...]:
        # Full blocklist minus every domain variant of the allowed site keys.
        with self._lock:
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

    def set_project(self, name: str | None) -> None:
        # Requirement 5: a "productive project" may allowlist specific
        # social sites while enforcement stays ON for everything else.
        with self._lock:
            self.active_project = name

    # ---------- monitoring hooks ----------

    @property
    def monitoring_active(self) -> bool:
        # Captures/analysis run only during focused work: BREAK of either
        # kind pauses monitoring (nudging someone on a sanctioned break or
        # away from the desk would be noise), OFF disables everything.
        return self.mode is Mode.ON

    def record_verdict(self, productive: bool, minutes: int) -> str | None:
        """Fold one analyzer verdict into the streak; return 'praise'/'nudge'/None.

        Requirement 4: nudge whenever unproductive; praise once per 30
        consecutive productive minutes (streak then restarts so a long
        session earns praise again every 30 min).
        """
        with self._lock:
            if not productive:
                self.productive_streak_min = 0
                return "nudge"
            self.productive_streak_min += minutes
            if self.productive_streak_min >= 30:
                self.productive_streak_min = 0
                return "praise"
            return None

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
