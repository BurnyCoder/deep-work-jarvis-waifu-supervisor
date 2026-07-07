# OpenAI vision productivity analyzer (requirement 3). Global context: the
# monitor thread saves one stitched capture every 5 minutes and feeds its
# path here; once BATCH_SIZE captures accumulate, ONE vision call judges the
# whole window and returns {productive, reason} as a typed object.
# Structured outputs via responses.parse:
# https://developers.openai.com/api/docs/guides/structured-outputs
# Vision input format: https://developers.openai.com/api/docs/guides/images-vision

import base64
import logging
from pathlib import Path

# pydantic BaseModel doubles as the JSON schema the API is forced to follow:
# https://docs.pydantic.dev/latest/concepts/models/
from pydantic import BaseModel

from deepwork.storage import ResultsStore

log = logging.getLogger(__name__)

# System prompt: sets the judging persona; the encouraging/gentle tone is a
# spec requirement ("encouraging/gentle reason").
SYSTEM_PROMPT = (
    "You are a gentle, encouraging productivity coach. You receive a series of "
    "labeled captures (all monitors plus webcam) taken 5 minutes apart during a "
    "deep-work session. Judge whether the user is overall working on their "
    "stated topic across the series. Screens showing code, documents, research "
    "or tools related to the topic are productive; social media, videos or "
    "games unrelated to the topic are not. Reply with productive true/false "
    "and one short, kind, encouraging sentence explaining why."
)


class ProductivityVerdict(BaseModel):
    # The exact JSON contract from the spec: productive yes/no + reason.
    productive: bool
    reason: str


# Agentic mode: is the user's AI coding agent still working? Judged from ONE
# capture per poll (fast cadence beats batched depth for this question).
AGENT_WATCH_PROMPT = (
    "You are watching a developer's screens for agentic engineering. Decide "
    "whether an AI coding agent (e.g. Claude Code, Cursor, Copilot, a "
    "terminal/IDE agent) is ACTIVELY WORKING on any monitor right now: look "
    "for streaming/generating output, running tools or commands, progress "
    "spinners, or 'esc to interrupt'-style status lines. It is NOT working "
    "if it shows a finished response waiting for user input, a permission "
    "prompt awaiting approval, or no agent is visible at all. Reply with "
    "agent_working true/false and one short sentence of evidence."
)


class AgentActivityVerdict(BaseModel):
    # Structured contract for the agent-watch poll.
    agent_working: bool
    reason: str


class AgentActivityChecker:
    """One-capture vision check: is the AI agent on screen still busy?"""

    def __init__(self, client, model: str, store: ResultsStore):
        self.client = client                      # openai.OpenAI or test fake
        self.model = model
        self.store = store

    def check(self, path: Path) -> AgentActivityVerdict:
        # Same responses.parse structured-output call as the productivity
        # analyzer, but a single low-detail image (85 tokens) per poll:
        # https://developers.openai.com/api/docs/guides/structured-outputs
        user_content = [
            {"type": "input_text", "text": "Current capture of all monitors follows."},
            {"type": "input_image", "image_url": _image_to_data_url(path),
             "detail": "low"},
        ]
        request = {"model": self.model,
                   "input": [{"role": "system", "content": AGENT_WATCH_PROMPT},
                             {"role": "user", "content": user_content}],
                   "text_format": AgentActivityVerdict}
        log.info("agent-watch request: model=%s capture=%s system=%r",
                 self.model, path.name, AGENT_WATCH_PROMPT)
        response = self.client.responses.parse(**request)
        verdict: AgentActivityVerdict = response.output_parsed
        log.info("agent-watch verdict: working=%s reason=%s",
                 verdict.agent_working, verdict.reason)
        stored_request = {**request,
                          "text_format": AgentActivityVerdict.__name__,
                          "input": [request["input"][0],
                                    {"role": "user",
                                     "content": [user_content[0],
                                                 {"type": "input_image",
                                                  "file": str(path)}]}]}
        self.store.save_llm_exchange("agent_watch", stored_request,
                                     response.model_dump(mode="json", warnings=False))
        return verdict


def _image_to_data_url(path: Path) -> str:
    # Vision API accepts base64 data URLs for local files:
    # https://developers.openai.com/api/docs/guides/images-vision#giving-a-model-images-as-input
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


class ProductivityAnalyzer:
    def __init__(self, client, model: str, store: ResultsStore, batch_size: int = 5):
        # client injected (real openai.OpenAI in prod, fake in tests).
        self.client = client
        self.model = model
        self.store = store
        self.batch_size = batch_size
        self._batch: list[Path] = []              # capture paths pending analysis

    def add_capture(self, path: Path, topic: str) -> ProductivityVerdict | None:
        """Queue one capture; when the batch is full, analyze and return the
        verdict (None while still accumulating)."""
        self._batch.append(path)
        if len(self._batch) < self.batch_size:
            log.info("capture batched (%d/%d)", len(self._batch), self.batch_size)
            return None
        batch, self._batch = self._batch, []      # take & reset atomically
        return self._analyze(batch, topic)

    def _analyze(self, batch: list[Path], topic: str) -> ProductivityVerdict:
        # User content: one text part naming the topic + one input_image per
        # capture. detail="low" costs a flat 85 tokens per image:
        # https://developers.openai.com/api/docs/guides/images-vision#specify-image-input-detail-level
        user_content = [{"type": "input_text",
                         "text": f"My deep-work topic: {topic}. "
                                 f"{len(batch)} captures follow, oldest first."}]
        user_content += [{"type": "input_image",
                          "image_url": _image_to_data_url(p),
                          "detail": "low"} for p in batch]
        request = {"model": self.model,
                   "input": [{"role": "system", "content": SYSTEM_PROMPT},
                             {"role": "user", "content": user_content}],
                   "text_format": ProductivityVerdict}
        # Log the full prompt (spec: prompts logged uncut) — image parts are
        # summarized in the LOG line only; the stored JSON keeps everything.
        log.info("vision request: model=%s topic=%r captures=%d system=%r",
                 self.model, topic, len(batch), SYSTEM_PROMPT)
        # responses.parse validates the reply against ProductivityVerdict and
        # retries malformed JSON at the API layer:
        # https://github.com/openai/openai-python#structured-outputs
        response = self.client.responses.parse(**request)
        verdict: ProductivityVerdict = response.output_parsed
        log.info("vision verdict: productive=%s reason=%s",
                 verdict.productive, verdict.reason)
        # Persist the whole exchange; data URLs are elided from the stored
        # request (the JPEGs already live in results/captures/).
        stored_request = {**request,
                          "text_format": ProductivityVerdict.__name__,
                          "input": [request["input"][0],
                                    {"role": "user",
                                     "content": [user_content[0]] +
                                                [{"type": "input_image",
                                                  "file": str(p)} for p in batch]}]}
        # mode="json" + warnings=False silences pydantic's union-serializer
        # noise when dumping the SDK's ParsedResponse (harmless but loud):
        # https://docs.pydantic.dev/latest/concepts/serialization/#serialization-warnings
        self.store.save_llm_exchange("vision", stored_request,
                                     response.model_dump(mode="json", warnings=False))
        return verdict
