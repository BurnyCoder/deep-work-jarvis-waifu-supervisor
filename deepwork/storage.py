# Results storage (requirement 8): every artifact the app produces lands
# under results/ — stitched capture JPEGs, full LLM request/response JSON,
# per-day session event logs, and the persisted state (allowance + topics).
# pathlib file IO: https://docs.python.org/3/library/pathlib.html

import json
import logging
import threading
from datetime import datetime
from pathlib import Path

from PIL import Image

log = logging.getLogger(__name__)


def _stamp(now: datetime | None = None) -> str:
    # One shared timestamp format for filenames: sortable microsecond precision
    # prevents rapid same-kind LLM exchanges from overwriting each other.
    # strftime codes: https://docs.python.org/3/library/datetime.html#format-codes
    return f"{now or datetime.now():%Y%m%d_%H%M%S_%f}"


class ResultsStore:
    def __init__(self, results_dir: str | Path):
        self.root = Path(results_dir)
        # Create the folder tree up front (mkdir -p semantics):
        # https://docs.python.org/3/library/pathlib.html#pathlib.Path.mkdir
        for sub in ("captures", "llm", "sessions"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        # Session events can arrive from Flask and scheduler threads. One lock
        # preserves JSONL order, while the pending list retains complete lines
        # across a transient append failure for a later retry. RLock supports
        # nested same-thread helpers: https://docs.python.org/3/library/threading.html#rlock-objects
        self._session_event_lock = threading.RLock()
        self._pending_session_lines: list[tuple[str, str]] = []

    def save_capture(self, image: Image.Image) -> Path:
        """Write one stitched capture as a timestamped JPEG; return its path."""
        path = self.root / "captures" / f"{_stamp()}.jpg"
        # quality=80 halves file size versus default with negligible loss for
        # screen content: https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#jpeg
        image.save(path, "JPEG", quality=80)
        log.info("capture saved: %s", path.name)
        return path

    def save_llm_exchange(self, kind: str, request: dict, response: dict) -> Path:
        """Persist one FULL LLM request/response pair as JSON (never truncated
        — spec: 'written into logs without being cut off')."""
        path = self.root / "llm" / f"{_stamp()}_{kind}.json"
        payload = {"kind": kind, "ts": datetime.now().isoformat(),
                   "request": request, "response": response}
        # ensure_ascii=False keeps unicode readable; indent for humans:
        # https://docs.python.org/3/library/json.html#json.dump
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8")
        return path

    def append_session_event(self, event: dict) -> None:
        """Append one timestamped event to today's session JSONL file —
        JSON Lines: one object per line (https://jsonlines.org/)."""
        now = datetime.now()
        filename = f"{now:%Y%m%d}.jsonl"
        line = json.dumps(
            {"ts": now.isoformat(), **event},
            ensure_ascii=False,
            default=str,
        )
        with self._session_event_lock:
            self._pending_session_lines.append((filename, line))
            self._flush_session_events_locked()

    def _flush_session_events_locked(self) -> None:
        """Append pending lines oldest-first while the event lock is held."""

        while self._pending_session_lines:
            filename, line = self._pending_session_lines[0]
            path = self.root / "sessions" / filename
            payload = (line + "\n").encode("utf-8")
            original_size = path.stat().st_size if path.exists() else 0
            try:
                self._append_session_payload(path, payload)
            except Exception:
                # A write, flush, or close can fail after persisting bytes.
                # Restore the pre-append boundary before retaining the complete
                # line for retry, preventing duplicate or corrupt JSONL rows.
                try:
                    if path.exists():
                        with path.open("r+b") as rollback:
                            rollback.truncate(original_size)
                except Exception:
                    log.exception("session-event append rollback failed: %s", path)
                raise
            self._pending_session_lines.pop(0)

    @staticmethod
    def _append_session_payload(path: Path, payload: bytes) -> None:
        """Append one complete encoded line or raise for rollback by the caller."""

        with path.open("ab") as handle:
            written = handle.write(payload)
            if written != len(payload):
                raise OSError(
                    f"short session-event write: {written}/{len(payload)} bytes"
                )

    def retry_session_events(self) -> None:
        """Retry any complete JSONL lines retained after an append failure."""

        with self._session_event_lock:
            self._flush_session_events_locked()

    @property
    def session_events_pending(self) -> bool:
        """Report whether feedback must wait for earlier event persistence."""

        with self._session_event_lock:
            return bool(self._pending_session_lines)

    # ---------- state persistence (used by SessionState) ----------

    def save_state(self, data: dict) -> None:
        (self.root / "state.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_state(self) -> dict:
        path = self.root / "state.json"
        # Missing file = first run → empty dict, no special-casing upstream.
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
