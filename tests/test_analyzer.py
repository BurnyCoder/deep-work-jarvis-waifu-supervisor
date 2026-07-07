# Tests for deepwork/monitoring/analyzer.py with a FAKE OpenAI client — no
# network, no key. The fake mirrors the two SDK members the analyzer touches:
# client.responses.parse(...) and the returned .output_parsed, per
# https://developers.openai.com/api/docs/guides/structured-outputs

from PIL import Image

from deepwork.monitoring.analyzer import (
    SYSTEM_PROMPT,
    AgentActivityChecker,
    AgentActivityVerdict,
    ProductivityAnalyzer,
    ProductivityVerdict,
)
from deepwork.storage import ResultsStore


class FakeResponses:
    def __init__(self, verdict):
        self.verdict = verdict
        self.last_kwargs = None

    def parse(self, **kwargs):
        self.last_kwargs = kwargs                  # captured for assertions
        verdict = self.verdict                     # close over, not R's self
        # Minimal stand-in for openai.types.responses.ParsedResponse
        class R:
            output_parsed = verdict
            def model_dump(self, **kwargs):        # analyzer persists this
                return {"output_parsed": verdict.model_dump()}
        return R()


class FakeClient:
    def __init__(self, verdict):
        self.responses = FakeResponses(verdict)


def test_verdict_requires_observed_description():
    # The nudge/praise TTS quotes what was seen, so `observed` is a REQUIRED
    # part of the vision contract, and the system prompt must ask for it.
    v = ProductivityVerdict(productive=False, reason="off-topic",
                            observed="Twitter feed open on monitor 2")
    assert "Twitter" in v.observed
    assert "observed" in SYSTEM_PROMPT           # prompt requests the field
    assert "concrete" in SYSTEM_PROMPT.lower()   # ...and concrete specifics


def make_analyzer(tmp_path, verdict=None, batch_size=2):
    verdict = verdict or ProductivityVerdict(productive=True, reason="deep in code",
                                             observed="IDE with tests running")
    client = FakeClient(verdict)
    store = ResultsStore(tmp_path)
    analyzer = ProductivityAnalyzer(client=client, model="test-model",
                                    store=store, batch_size=batch_size)
    return analyzer, client, store


def save_capture(store):
    return store.save_capture(Image.new("RGB", (8, 8), "blue"))


def test_batch_accumulates_until_size_then_analyzes(tmp_path):
    analyzer, client, store = make_analyzer(tmp_path, batch_size=2)
    # First capture: below batch size → no API call yet.
    assert analyzer.add_capture(save_capture(store), topic="thesis") is None
    assert client.responses.last_kwargs is None
    # Second capture: batch full → one vision call, verdict returned.
    verdict = analyzer.add_capture(save_capture(store), topic="thesis")
    assert verdict is not None and verdict.productive


def test_request_shape_matches_responses_api(tmp_path):
    analyzer, client, store = make_analyzer(tmp_path, batch_size=2)
    analyzer.add_capture(save_capture(store), topic="thesis")
    analyzer.add_capture(save_capture(store), topic="thesis")
    kwargs = client.responses.last_kwargs
    assert kwargs["model"] == "test-model"
    assert kwargs["text_format"] is ProductivityVerdict
    user_content = kwargs["input"][-1]["content"]
    images = [c for c in user_content if c["type"] == "input_image"]
    assert len(images) == 2                        # every batched capture sent
    # Images ride as base64 data URLs with low detail (85 tokens flat/image):
    # https://developers.openai.com/api/docs/guides/images-vision
    assert all(i["image_url"].startswith("data:image/jpeg;base64,") for i in images)
    assert all(i["detail"] == "low" for i in images)
    # The user's topic is in the text part so the model judges relevance.
    texts = [c for c in user_content if c["type"] == "input_text"]
    assert any("thesis" in t["text"] for t in texts)


def test_agent_activity_checker_request_shape_and_persistence(tmp_path):
    verdict = AgentActivityVerdict(agent_working=True, reason="tokens streaming")
    client = FakeClient(verdict)
    store = ResultsStore(tmp_path)
    checker = AgentActivityChecker(client=client, model="test-model", store=store)

    result = checker.check(save_capture(store))
    assert result.agent_working is True
    kwargs = client.responses.last_kwargs
    assert kwargs["model"] == "test-model"
    assert kwargs["text_format"] is AgentActivityVerdict
    user_content = kwargs["input"][-1]["content"]
    images = [c for c in user_content if c["type"] == "input_image"]
    # Exactly ONE low-detail capture per check (fast 60s cadence, cheap).
    assert len(images) == 1 and images[0]["detail"] == "low"
    assert images[0]["image_url"].startswith("data:image/jpeg;base64,")
    # Full exchange persisted under its own kind for auditability.
    assert list((tmp_path / "llm").glob("*_agent_watch.json"))


def test_exchange_persisted_uncut_and_batch_reset(tmp_path):
    analyzer, client, store = make_analyzer(tmp_path, batch_size=2)
    analyzer.add_capture(save_capture(store), topic="t")
    analyzer.add_capture(save_capture(store), topic="t")
    saved = list((tmp_path / "llm").glob("*.json"))
    assert len(saved) == 1                         # full request+response JSON
    # Batch resets after analysis — next capture starts a fresh batch.
    assert analyzer.add_capture(save_capture(store), topic="t") is None
