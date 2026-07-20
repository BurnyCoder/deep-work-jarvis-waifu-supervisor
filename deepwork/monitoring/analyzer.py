# OpenAI vision productivity analyzer (requirement 3). Global context: every
# five-minute monitor tick appends one stitched capture to a bounded rolling
# window, then one vision call compares all currently available captures.
# OpenAI supports multiple images in one Responses content array:
# https://developers.openai.com/api/docs/guides/images-vision#giving-a-model-images-as-input
# Structured outputs via responses.parse:
# https://developers.openai.com/api/docs/guides/structured-outputs
# Vision input format: https://developers.openai.com/api/docs/guides/images-vision

import base64
import logging
from collections import deque
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
    "deep-work session, ordered oldest to newest. Each chronological capture is "
    "one stitched image containing simultaneous panels labeled Monitor 1, "
    "Monitor 2, and Webcam; those panels are not separate chronological captures. "
    "Use the explicit chronological capture labels as the only timeline. Judge both whether the work "
    "matches the stated topic and whether meaningful visible progress is being "
    "made across the series. Compare changes in documents, code, tests, task "
    "state, research, visible content, and the user's presence. With only one "
    "capture, judge current task alignment and explicitly avoid claiming a "
    "trend that cannot yet be seen. If that single capture shows genuine "
    "task-aligned engagement, you must set productive true; missing comparison "
    "history alone must never make the verdict false. For exactly one capture, "
    "the observed field must describe only the current scene and end with "
    "'No chronological comparison is available yet'; never call it progress, "
    "no progress, advanced, or stalled. Before the configured full window, "
    "use visible changes as evidence, but mark productive false only for visible "
    "distraction, off-topic activity, or clear non-work—not merely because the "
    "window is incomplete or looks unchanged. Obey the evaluation phase rule "
    "in the user message. When a full window shows no meaningful "
    "progress, mark productive false and explain the stall gently. Do not "
    "penalize plausibly productive reading, thinking, calls, builds, or other "
    "work whose progress may not visibly change if the captures contain "
    "evidence of genuine engagement. Social media and video are unproductive "
    "unless the user message explicitly lists that website group as required "
    "for the task and the visible activity serves the stated topic; unrelated "
    "feeds, videos, and games remain unproductive. Reply with: productive "
    "true/false; reason - one short, "
    "kind, speech-ready sentence naming the concrete progress or lack of "
    "progress; and observed - a concrete comparison of what changed or stayed "
    "static from oldest to newest (name visible apps, sites, window titles, "
    "content, monitors, and webcam presence) so a coach can quote it back."
)


class ProductivityVerdict(BaseModel):
    # The exact JSON contract from the spec: productive yes/no + reason —
    # plus `observed`, the concrete what-I-saw description the TTS messages
    # quote back to the user ("you had Twitter open on monitor 2...").
    productive: bool
    reason: str
    observed: str


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
        log.info(
            "agent-watch request: model=%s capture=%s system=%r user=%r",
            self.model,
            path.name,
            AGENT_WATCH_PROMPT,
            user_content[0]["text"],
        )
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
    def __init__(self, client, model: str, store: ResultsStore,
                 window_size: int = 5, reasoning_effort: str = "xhigh"):
        # client injected (real openai.OpenAI in prod, fake in tests).
        if window_size < 1:
            raise ValueError("window_size must be at least 1")
        self.client = client
        self.model = model
        self.store = store
        self.window_size = window_size
        self.reasoning_effort = reasoning_effort
        # A bounded deque automatically evicts the oldest item on append:
        # https://docs.python.org/3/library/collections.html#collections.deque
        self._window: deque[Path] = deque(maxlen=window_size)

    def reset(self) -> None:
        """Start a fresh progress window for a newly started work session."""
        self._window.clear()
        log.info("progress window reset")

    def add_capture(
        self,
        path: Path,
        topic: str,
        allowed_sites: tuple[str, ...] = (),
    ) -> ProductivityVerdict:
        """Append one capture and evaluate every available recent capture."""
        self._window.append(path)
        window = list(self._window)                # stable oldest→newest snapshot
        log.info("progress window updated (%d/%d): %s",
                 len(window), self.window_size,
                 ", ".join(capture.name for capture in window))
        return self._analyze(window, topic, allowed_sites)

    def _analyze(
        self,
        window: list[Path],
        topic: str,
        allowed_sites: tuple[str, ...],
    ) -> ProductivityVerdict:
        # User content: one text part naming the topic + one input_image per
        # capture. Multiple images in one content array are documented at:
        # https://developers.openai.com/api/docs/guides/images-vision#giving-a-model-images-as-input
        # detail="low" keeps this frequent comparison fast and inexpensive:
        # https://developers.openai.com/api/docs/guides/images-vision#specify-image-input-detail-level
        # Put the rule next to the changing window count. This measured prompt
        # fix prevents an incomplete but unchanged window from being called
        # stalled, while still allowing visible distraction to be caught.
        if len(window) < self.window_size:
            phase_rule = (
                f"WARM-UP ({len(window)}/{self.window_size}): do not infer a "
                "stall. If the captures are task-aligned with no visible "
                "distraction, off-topic activity, or clear non-work, productive "
                "MUST be true even when the visible scene is unchanged."
            )
        else:
            phase_rule = (
                f"FULL WINDOW ({len(window)}/{self.window_size}): compare the "
                "whole window; genuinely unchanged on-topic work may be marked "
                "stalled, subject to the reading/thinking/build caveat."
            )
        capture_summary = (
            "1 chronological capture follows"
            if len(window) == 1
            else f"{len(window)} chronological captures follow"
        )
        if allowed_sites:
            access_rule = (
                "Work-required website groups explicitly allowed for this "
                f"task: {', '.join(allowed_sites)}. Seeing an allowed site "
                "does not automatically make the activity productive; it must "
                "show activity that visibly serves the stated topic. Unrelated "
                "scrolling remains "
                "unproductive."
            )
        else:
            access_rule = (
                "No distracting website groups are explicitly allowed for "
                "this task."
            )
        header = {"type": "input_text",
                  "text": f"My deep-work topic: {topic}. "
                          f"{access_rule} "
                          f"{capture_summary}, oldest first. "
                          f"{phase_rule}"}
        user_content = [header]
        stored_content = [header]
        for index, path in enumerate(window, start=1):
            # Interleaved labels make the temporal boundary explicit: each
            # following image is one simultaneous multi-monitor/webcam composite.
            label = {
                "type": "input_text",
                "text": f"Chronological capture {index} of {len(window)}: "
                        "one stitched image with simultaneous monitor/webcam panels.",
            }
            user_content.extend([
                label,
                {"type": "input_image",
                 "image_url": _image_to_data_url(path),
                 "detail": "low"},
            ])
            # Persist the same uncut text prompt while referring to the already
            # stored JPEG instead of duplicating its large base64 payload.
            stored_content.extend([
                label,
                {"type": "input_image", "file": str(path)},
            ])
        request = {"model": self.model,
                   # Responses nests effort under `reasoning`; GPT-5.6 supports
                   # xhigh for quality-first work:
                   # https://developers.openai.com/api/docs/guides/latest-model
                   "reasoning": {"effort": self.reasoning_effort},
                   "input": [{"role": "system", "content": SYSTEM_PROMPT},
                             {"role": "user", "content": user_content}],
                   "text_format": ProductivityVerdict}
        # Log every textual prompt part uncut; name image files instead of
        # dumping base64 bytes because the exact JPEGs are already persisted.
        prompt_text = [
            SYSTEM_PROMPT,
            *(part["text"] for part in user_content
              if part["type"] == "input_text"),
        ]
        log.info(
            "vision request: model=%s reasoning=%s prompt=%r capture_files=%s",
            self.model,
            self.reasoning_effort,
            prompt_text,
            ", ".join(path.name for path in window),
        )
        # responses.parse validates the reply against ProductivityVerdict and
        # retries malformed JSON at the API layer:
        # https://github.com/openai/openai-python#structured-outputs
        response = self.client.responses.parse(**request)
        verdict: ProductivityVerdict = response.output_parsed
        log.info(
            "vision output: productive=%s reason=%s observed=%s",
            verdict.productive,
            verdict.reason,
            verdict.observed,
        )
        # Persist the whole exchange; data URLs are elided from the stored
        # request (the JPEGs already live in results/captures/).
        stored_request = {**request,
                          "text_format": ProductivityVerdict.__name__,
                          "input": [request["input"][0],
                                    {"role": "user",
                                     "content": stored_content}]}
        # mode="json" + warnings=False silences pydantic's union-serializer
        # noise when dumping the SDK's ParsedResponse (harmless but loud):
        # https://docs.pydantic.dev/latest/concepts/serialization/#serialization-warnings
        self.store.save_llm_exchange("vision", stored_request,
                                     response.model_dump(mode="json", warnings=False))
        return verdict
