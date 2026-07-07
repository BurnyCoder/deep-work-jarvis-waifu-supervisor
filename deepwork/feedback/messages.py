# LLM-generated feedback messages (requirement 4): the words spoken to the
# user are never canned — a text model writes each good-luck, nudge, praise
# and break acknowledgment from live context (topic, verdict reason, break
# purpose). One shared generate() path = no duplicated call code.
# Responses API text generation: https://github.com/openai/openai-python

import logging

from deepwork.storage import ResultsStore

log = logging.getLogger(__name__)

# One template per message kind; {placeholders} are filled by build_prompt.
# All ask for ONE short spoken sentence because TTS reads the result aloud.
_TEMPLATES = {
    "good_luck": (
        "A user is starting a deep-work session on the topic: {topic!r}. "
        "Write one short, warm, motivating spoken sentence wishing them good "
        "luck on that topic. No emojis, it will be read aloud."
    ),
    "nudge": (
        "A user working on {topic!r} was just seen being unproductive — the "
        "monitor said: {reason!r}. Write one short, gentle, kind spoken "
        "sentence nudging them back to work without guilt-tripping. "
        "No emojis, it will be read aloud."
    ),
    "praise": (
        "A user working on {topic!r} has stayed focused for 30 minutes "
        "straight — the monitor said: {reason!r}. Write one short, sincere "
        "spoken sentence congratulating them. No emojis, it will be read aloud."
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
    return _TEMPLATES[kind].format_map(context)


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
