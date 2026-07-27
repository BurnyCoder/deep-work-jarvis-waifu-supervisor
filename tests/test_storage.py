# Tests for deepwork/storage.py — everything writes under a pytest tmp_path
# acting as the results/ folder (requirement 8).

import json

import pytest
from PIL import Image

from deepwork.storage import ResultsStore


def test_creates_subfolders(tmp_path):
    ResultsStore(tmp_path)
    assert (tmp_path / "captures").is_dir()
    assert (tmp_path / "llm").is_dir()
    assert (tmp_path / "sessions").is_dir()


def test_save_capture_writes_timestamped_jpeg(tmp_path):
    store = ResultsStore(tmp_path)
    path = store.save_capture(Image.new("RGB", (10, 10), "red"))
    assert path.exists() and path.suffix == ".jpg"
    assert path.parent.name == "captures"
    # Filename starts with a YYYYMMDD stamp for chronological sorting.
    assert path.name[:8].isdigit()


def test_save_llm_exchange_round_trips_uncut(tmp_path):
    # Spec: "all prompts and outputs from LLMs are written into logs without
    # being cut off" — the JSON file must hold the full payloads verbatim.
    store = ResultsStore(tmp_path)
    request = {"model": "m", "input": [{"role": "user", "content": "x" * 5000}]}
    response = {"productive": True, "reason": "looks focused"}
    path = store.save_llm_exchange("vision", request, response)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["request"] == request              # byte-identical round trip
    assert data["response"] == response
    assert data["kind"] == "vision"


def test_rapid_llm_exchanges_get_distinct_timestamped_files(tmp_path):
    # Rolling-window tests and accelerated smoke runs can finish more than one
    # same-kind request inside a second; no full exchange may be overwritten.
    store = ResultsStore(tmp_path)
    first = store.save_llm_exchange("vision", {"input": "one"}, {"output": "one"})
    second = store.save_llm_exchange("vision", {"input": "two"}, {"output": "two"})
    assert first != second
    assert first.exists() and second.exists()


def test_session_events_append_as_jsonl(tmp_path):
    store = ResultsStore(tmp_path)
    store.append_session_event({"event": "session_start", "topic": "thesis"})
    store.append_session_event({"event": "verdict", "productive": False})
    files = list((tmp_path / "sessions").glob("*.jsonl"))
    assert len(files) == 1                         # one file per day
    lines = files[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2                         # one JSON object per line
    assert json.loads(lines[0])["topic"] == "thesis"
    assert "ts" in json.loads(lines[0])            # events are timestamped


@pytest.mark.parametrize("failure_mode", ["partial", "after_full_write"])
def test_session_event_line_survives_transient_append_failure(
    tmp_path,
    monkeypatch,
    failure_mode,
):
    """Partial and close-like failures roll back before one exact retry."""

    store = ResultsStore(tmp_path)
    original_append = store._append_session_payload
    failures = {"remaining": 1}

    def fail_once(path, payload):
        if failures["remaining"]:
            failures["remaining"] -= 1
            if failure_mode == "partial":
                with path.open("ab") as handle:
                    handle.write(payload[: max(1, len(payload) // 2)])
            else:
                original_append(path, payload)
            raise OSError("disk temporarily unavailable")
        return original_append(path, payload)

    monkeypatch.setattr(store, "_append_session_payload", fail_once)

    with pytest.raises(OSError, match="temporarily unavailable"):
        store.append_session_event({"event": "goal_access_started"})
    assert store.session_events_pending is True
    failed_file = next((tmp_path / "sessions").glob("*.jsonl"))
    assert failed_file.read_bytes() == b""

    store.retry_session_events()

    assert store.session_events_pending is False
    event_file = next((tmp_path / "sessions").glob("*.jsonl"))
    event = json.loads(event_file.read_text(encoding="utf-8"))
    assert event["event"] == "goal_access_started"
    assert "ts" in event


def test_state_persistence_round_trip(tmp_path):
    store = ResultsStore(tmp_path)
    assert store.load_state() == {}                # first run → empty dict
    store.save_state({"previous_topics": ["a"]})
    assert store.load_state() == {"previous_topics": ["a"]}
