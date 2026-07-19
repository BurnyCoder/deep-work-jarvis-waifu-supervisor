# Task-scoped website-access policy. Global context: the Flask form,
# SessionState, projects.json loader, dashboard, and vision prompt all need one
# authoritative interpretation of a "site group"; this module validates and
# orders those keys without knowing anything about HTTP, threads, or blocking.
# Server-side allowlist validation is required even when the browser renders
# fixed checkboxes: https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html

import json
import logging
from collections.abc import Iterable, Mapping
from pathlib import Path

from deepwork.config import SITE_DOMAINS

log = logging.getLogger(__name__)

# Human labels live beside the policy instead of being reimplemented by every
# UI consumer. Keys remain the stable machine values stored in logs/status.
SITE_LABELS: dict[str, str] = {
    "reddit": "Reddit",
    "youtube": "YouTube",
    "twitter": "X / Twitter",
    "discord": "Discord",
    "hackernews": "Hacker News",
    "linkedin": "LinkedIn",
    "bluesky": "Bluesky",
    "substack": "Substack",
    "facebook": "Facebook",
    "lesswrong": "LessWrong",
    "eaforum": "EA Forum",
    "4chan": "4chan",
}


def site_options() -> tuple[tuple[str, str], ...]:
    """Return stable (key, label) choices in SITE_DOMAINS configuration order."""

    # Dict iteration preserves insertion order:
    # https://docs.python.org/3/library/stdtypes.html#dict
    return tuple((key, SITE_LABELS.get(key, key)) for key in SITE_DOMAINS)


def site_labels(values: Iterable[str]) -> tuple[str, ...]:
    """Return display labels for validated site keys in policy order."""

    return tuple(
        SITE_LABELS.get(key, key)
        for key in normalize_site_keys(values)
    )


def normalize_site_keys(values: Iterable[str]) -> tuple[str, ...]:
    """Validate, deduplicate, and order submitted website-group keys."""

    requested: set[str] = set()
    for value in values:
        # The policy rejects malformed programmatic callers as well as forged
        # form values; silently stringifying them could accidentally authorize
        # an unintended key.
        if not isinstance(value, str):
            raise ValueError("Website group values must be strings.")
        key = value.strip().lower()
        if not key:
            continue
        if key not in SITE_DOMAINS:
            raise ValueError(f"Unknown website group: {key}")
        requested.add(key)
    # Replaying config order makes logs, prompts, status, and tests deterministic.
    return tuple(key for key in SITE_DOMAINS if key in requested)


def resolve_work_allowed_sites(
    selected_sites: Iterable[str],
    project: str | None,
    project_allowlists: Mapping[str, Iterable[str]],
) -> tuple[str, ...]:
    """Combine a saved project preset with one-off task choices."""

    selected = normalize_site_keys(selected_sites)
    project_name = project.strip() if project else None
    preset: tuple[str, ...] = ()
    if project_name:
        if project_name not in project_allowlists:
            raise ValueError(f"Unknown project preset: {project_name}")
        preset = normalize_site_keys(project_allowlists[project_name])
    return normalize_site_keys((*preset, *selected))


def _validate_project_allowlists(data: object) -> dict[str, tuple[str, ...]]:
    """Validate the decoded projects.json shape before it reaches state."""

    if not isinstance(data, dict):
        raise ValueError("projects.json must contain a JSON object.")
    validated: dict[str, tuple[str, ...]] = {}
    for raw_name, raw_sites in data.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValueError("Every project preset needs a non-empty string name.")
        if not isinstance(raw_sites, list):
            raise ValueError(
                f"Project preset {raw_name!r} must contain an array of website groups."
            )
        name = raw_name.strip()
        if name in validated:
            raise ValueError(f"Duplicate project preset after trimming: {name}")
        validated[name] = normalize_site_keys(raw_sites)
    return validated


def load_project_allowlists(
    path: str | Path = Path("projects.json"),
) -> dict[str, tuple[str, ...]]:
    """Load optional saved project presets, failing early on bad configuration."""

    source = Path(path)
    if not source.exists():
        return {}
    try:
        # json.loads is the standard-library decoder:
        # https://docs.python.org/3/library/json.html#json.loads
        decoded = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source} must contain valid JSON: {exc.msg}") from exc
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Could not read {source}: {exc}") from exc
    validated = _validate_project_allowlists(decoded)
    log.info("project presets loaded: %d from %s", len(validated), source)
    return validated
