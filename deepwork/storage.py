# Results storage (requirement 8): every artifact the app produces lands
# under results/ — stitched capture JPEGs, full LLM request/response JSON,
# per-day session event logs, and the persisted state (allowance + topics).
# pathlib file IO: https://docs.python.org/3/library/pathlib.html

import json
import logging
from datetime import datetime
from pathlib import Path

from PIL import Image

log = logging.getLogger(__name__)


def _stamp(now: datetime | None = None) -> str:
    # One shared timestamp format for filenames: sortable, second precision.
    # strftime codes: https://docs.python.org/3/library/datetime.html#format-codes
    return f"{now or datetime.now():%Y%m%d_%H%M%S}"


class ResultsStore:
    def __init__(self, results_dir: str | Path):
        self.root = Path(results_dir)
        # Create the folder tree up front (mkdir -p semantics):
        # https://docs.python.org/3/library/pathlib.html#pathlib.Path.mkdir
        for sub in ("captures", "llm", "sessions"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

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
        path = self.root / "sessions" / f"{datetime.now():%Y%m%d}.jsonl"
        line = json.dumps({"ts": datetime.now().isoformat(), **event},
                          ensure_ascii=False, default=str)
        with path.open("a", encoding="utf-8") as f:   # append mode
            f.write(line + "\n")

    # ---------- state persistence (used by SessionState) ----------

    def save_state(self, data: dict) -> None:
        (self.root / "state.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_state(self) -> dict:
        path = self.root / "state.json"
        # Missing file = first run → empty dict, no special-casing upstream.
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
