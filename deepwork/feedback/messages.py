# LLM-generated feedback messages (requirement 4): the words spoken to the
# user are never canned — a text model writes each good-luck, nudge, praise,
# break acknowledgment, and temporary-access transition from live context.
# One shared generate() path = no duplicated call code.
# Responses API text generation: https://github.com/openai/openai-python

import logging

from deepwork.llm_output import record_response, require_output
from deepwork.storage import ResultsStore

log = logging.getLogger(__name__)

# One template per message kind; {placeholders} are filled by build_prompt.
# Short spoken output, but RICHLY grounded input: every template ends with
# the {session_context} block (topic, elapsed time, streak, allowance,
# recent concrete observations) so the voice can reference real specifics.
_CONTEXT_SUFFIX = (
    "\n\nCurrent session summary — ground what you say in these specifics:\n"
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
        "A user working on {topic!r} reached the app's 30-minute credited "
        "productive-streak milestone based on sampled evaluations. This is "
        "not continuous observation or proof of uninterrupted focus. The "
        "monitor's judgment: {reason!r}. The recorded evidence: {observed!r}. "
        "Write one or two sincere spoken sentences congratulating them on "
        "the milestone and the specific task-aligned work observed. Do not "
        "claim a measured duration of continuous focus. No emojis, it will "
        "be read aloud."
    ),
    "agent_running": (
        "The watcher now sees evidence that a user's AI coding agent is "
        "working: {reason!r}. Website blocking is relaxed while the agent "
        "is marked busy; app killing continues for apps without active "
        "permission. Write one short, friendly spoken sentence saying the "
        "agent appears busy and the user can take a moment. Do not claim "
        "that all apps are allowed or that completion is guaranteed. No "
        "emojis, it will be read aloud."
    ),
    "agent_done": (
        "The watcher no longer sees an actively working AI coding agent: "
        "{reason!r}. It may be finished, awaiting approval, or no longer "
        "visible; do not assume successful completion. Ordinary website "
        "policy has resumed, including task-required groups and any active "
        "goal access. Write one short, upbeat spoken sentence asking the "
        "user to check whether the agent needs input or has work to review, "
        "grounded in the observation. Do not claim that every non-task site "
        "was blocked. No emojis, it will be read aloud."
    ),
    "break_ack": (
        "A user is taking a {minutes}-minute break for: {purpose!r}. Write one "
        "short, friendly spoken sentence acknowledging the break and saying "
        "you'll see them back after it. No emojis, it will be read aloud."
    ),
    "break_end_ack": (
        "A user has ended their break for {purpose!r} after "
        "{charged_minutes} charged minute(s). Focus enforcement has resumed. "
        "Write one short, upbeat spoken sentence welcoming them back and "
        "encouraging them to return to their current task. No emojis, it will "
        "be read aloud."
    ),
    # State the goal, affected access groups, and transition constraint explicitly;
    # OpenAI's current model guidance recommends outcome-focused prompts with
    # concrete goals, relevant context, constraints, and success criteria:
    # https://developers.openai.com/api/docs/guides/latest-model#prompting-best-practices
    "goal_access_start": (
        "A user has started a temporary goal-scoped exception for website/app "
        "access for the explicit goal: {goal!r}. Its selected access groups "
        "are: {group_labels!r}. The access duration is "
        "{duration_description}. Starting this exception does not imply that "
        "every selected group was blocked immediately beforehand, because "
        "another active policy may already permit one. Write one short, "
        "friendly spoken sentence confirming only the temporary exception "
        "and reminding them to use it specifically for that goal. No emojis, "
        "it will be read aloud."
    ),
    "goal_access_end": (
        "The temporary goal-scoped exception for website/app access for the "
        "explicit goal {goal!r} has ended. Its selected access groups were: "
        "{group_labels!r}. The exception ended because: {end_reason!r}. This "
        "removes only this grant's permission; it does not claim that every "
        "selected group is now blocked, because another active policy may "
        "still permit one. Write one short, supportive spoken sentence "
        "acknowledging the outcome and directing the user back to their "
        "current task without overstating effective enforcement. No emojis, "
        "it will be read aloud."
    ),
    "verdict_correction": (
        "The user {correction_action} for the latest productivity evaluation "
        "from {from_label!r} to {to_label!r}. Write one short, neutral spoken "
        "sentence confirming that the saved evaluation will count as "
        "{to_label!r}. Do not praise, do not nudge, do not challenge the "
        "correction, and do not reassess or reinterpret the visual evidence. "
        "No emojis, it will be read aloud."
    ),
}


def build_prompt(kind: str, **context) -> str:
    # str.format_map fills only the placeholders the template mentions:
    # https://docs.python.org/3/library/stdtypes.html#str.format_map
    # Default only the optional summary; missing kind-specific fields still raise.
    context.setdefault("session_context", "(no session context available)")
    return (_TEMPLATES[kind] + _CONTEXT_SUFFIX).format_map(context)


class MessageGenerator:
    def __init__(
        self,
        client,
        model: str,
        store: ResultsStore,
        reasoning_effort: str = "medium",
    ):
        self.client = client                      # openai.OpenAI or test fake
        self.model = model
        self.store = store
        self.reasoning_effort = reasoning_effort

    def generate(self, kind: str, **context) -> str:
        """Build the prompt for `kind`, call the text model, log + persist the
        full exchange, and return the sentence to speak."""
        prompt = build_prompt(kind, **context)
        # Log the complete request prompt and active quality settings in one
        # timestamped record; the logging formatter supplies the timestamp.
        log.info(
            "message request (%s): model=%s reasoning=%s prompt=%s",
            kind,
            self.model,
            self.reasoning_effort,
            prompt,
        )
        # responses.create is the current plain-text generation call;
        # reasoning.effort is the documented quality control, while
        # output_text concatenates the model's text parts:
        # https://developers.openai.com/api/docs/guides/reasoning#get-started-with-reasoning
        # https://github.com/openai/openai-python#usage
        response = self.client.responses.create(
            model=self.model,
            reasoning={"effort": self.reasoning_effort},
            input=prompt,
        )
        record_response(
            response, logger=log, store=self.store, kind="message",
            request={
                "model": self.model,
                "reasoning": {"effort": self.reasoning_effort},
                "kind": kind,
                "input": prompt,
            },
        )
        # Refusal/empty replies stay in the audit trail without becoming speech.
        text = require_output(response.output_text, kind="message").strip()
        log.info("message output (%s): %s", kind, text)     # full output, uncut
        return text
