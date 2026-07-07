# Tests for deepwork/storage.py — everything writes under a pytest tmp_path
# acting as the results/ folder (requirement 8).

import json

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


def test_state_persistence_round_trip(tmp_path):
    store = ResultsStore(tmp_path)
    assert store.load_state() == {}                # first run → empty dict
    store.save_state({"previous_topics": ["a"]})
    assert store.load_state() == {"previous_topics": ["a"]}
