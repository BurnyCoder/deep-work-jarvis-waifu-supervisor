# Shared response handling: keep returned model evidence before consumers decide
# whether it can become a verdict or spoken feedback. Refusals can have no parsed
# output: https://developers.openai.com/api/docs/guides/structured-outputs

import json  # Serialize the complete response without truncating its text.
import logging  # Use the caller's logger and the configured file/terminal handlers.

from deepwork.storage import ResultsStore  # Keep the existing exchange-file format.


def record_response(response, *, logger: logging.Logger, store: ResultsStore,
                    kind: str, request: dict) -> None:
    """Record returned evidence, then reject an explicit non-completed status."""
    # JSON mode serializes SDK/Pydantic values; warnings=False avoids serializer
    # diagnostics without dropping fields from the recorded response:
    # https://docs.pydantic.dev/latest/concepts/serialization/
    payload = response.model_dump(mode="json", warnings=False)
    # Logging first retains the returned evidence if the subsequent file write fails.
    logger.info("%s response: %s", kind, json.dumps(payload, ensure_ascii=False))
    # The caller supplies image-file references instead of input base64 bytes.
    store.save_llm_exchange(kind, request, payload)
    # Partial text or parsed data cannot establish completion. Minimal injected
    # test replies may omit status; real Responses objects provide this field:
    # https://developers.openai.com/api/docs/guides/structured-outputs
    status = payload.get("status")
    if status is not None and status != "completed":
        raise ValueError(f"{kind} response status is {status!r}; no usable output")


def require_output[T](output: T | None, *, kind: str) -> T:
    """Reject missing verdicts and blank speech after their response is recorded."""
    # A refusal has no parsed verdict; empty/whitespace text cannot become speech.
    if output is None or (isinstance(output, str) and not output.strip()):
        raise ValueError(f"{kind} response contains no usable output")
    return output  # Preserve valid content; text callers may trim for playback.
