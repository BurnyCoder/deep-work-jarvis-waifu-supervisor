# LLM-generated feedback messages (requirement 4): the words spoken to the
# user are never canned — a text model writes each good-luck, nudge, praise
# and break acknowledgment from live context (topic, verdict reason, break
# purpose). One shared generate() path = no duplicated call code.
# Responses API text generation: https://github.com/openai/openai-python

import logging

from deepwork.storage import ResultsStore

log = logging.getLogger(__name__)

# One template per message kind; {placeholders} are filled by build_prompt.
# Short spoken output, but RICHLY grounded input: every template ends with
# the {session_context} block (topic, elapsed time, streak, allowance,
# recent concrete observations) so the voice can reference real specifics.
_CONTEXT_SUFFIX = (
    "\n\nFull session context — ground what you say in these specifics:\n"
    "{session_context}"
)

_TEMPLATES = {
    "good_luck": (
        "A user is starting a deep-work session on the topic: {topic!r}. "
        "Write one short, warm, motivating spoken sentence wishing them good "
        "luck on that topic. No emojis, it will be read aloud."
    ),
    "nudge": (
        "A user working on {topic!r} was just seen being unproductive. The "
        "monitor's judgment: {reason!r}. What was concretely on their screens: "
        "{observed!r}. Write one or two gentle, kind spoken sentences nudging "
        "them back to work without guilt-tripping — MENTION concretely what "
        "they were seen doing (name the site/app/content from the observation) "
        "so they know you actually saw it. No emojis, it will be read aloud."
    ),
    "praise": (
        "A user working on {topic!r} has stayed focused for 30 minutes "
        "straight. The monitor's judgment: {reason!r}. What was concretely on "
        "their screens: {observed!r}. Write one or two sincere spoken "
        "sentences congratulating them — name the focused work you saw them "
        "doing. No emojis, it will be read aloud."
    ),
    "agent_running": (
        "A user's AI coding agent just started working on their task, so "
        "they're free to relax or browse until it finishes — the monitor "
        "said: {reason!r}. Write one short, friendly spoken sentence telling "
        "them the agent is running and they can take it easy for a bit. "
        "No emojis, it will be read aloud."
    ),
    "agent_done": (
        "A user's AI coding agent has just FINISHED and is waiting for their "
        "review — the monitor said: {reason!r}. Non-task websites were just "
        "re-blocked; any websites explicitly required for the task remain "
        "available. Write one short, upbeat spoken sentence telling them the "
        "agent is done and it's time to come back and review its work. No "
        "emojis, it will be read aloud."
    ),
    "break_ack": (
        "A user is taking a {minutes}-minute break for: {purpose!r}. Write one "
        "short, friendly spoken sentence acknowledging the break and saying "
        "you'll see them back after it. No emojis, it will be read aloud."
    ),
}


def build_prompt(kind: str, **context) -> str:
    # str.format_map fills only the placeholders the template mentions:
    # https://docs.python.org/3/library/stdtypes.html#str.format_map
    # session_context defaults to a stub so ad-hoc calls never KeyError.
    context.setdefault("session_context", "(no session context available)")
    return (_TEMPLATES[kind] + _CONTEXT_SUFFIX).format_map(context)


class MessageGenerator:
    def __init__(self, client, model: str, store: ResultsStore):
        self.client = client                      # openai.OpenAI or test fake
        self.model = model
        self.store = store

    def generate(self, kind: str, **context) -> str:
        """Build the prompt for `kind`, call the text model, log + persist the
        full exchange, and return the sentence to speak."""
        prompt = build_prompt(kind, **context)
        log.info("message prompt (%s): %s", kind, prompt)   # full prompt, uncut
        # responses.create is the current plain-text generation call;
        # output_text concatenates the model's text parts:
        # https://github.com/openai/openai-python#usage
        response = self.client.responses.create(model=self.model, input=prompt)
        text = response.output_text.strip()
        log.info("message output (%s): %s", kind, text)     # full output, uncut
        self.store.save_llm_exchange("message",
                                     {"model": self.model, "kind": kind, "input": prompt},
                                     response.model_dump())
        return text
