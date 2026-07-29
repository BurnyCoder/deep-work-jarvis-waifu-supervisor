# Unified website-and-app access policy. Global context: Flask forms, session
# state, process/hosts enforcement, prompts, status, and projects.json all need
# one authoritative interpretation of an "access group." This module owns that
# vocabulary and validation without depending on HTTP, threads, or blockers.
# Server-side allowlist validation remains necessary for fixed checkbox forms:
# https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html

import json
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from deepwork.config import APP_PROCESSES, SITE_DOMAINS

# Module-level logging lets project-preset loading appear in both the terminal
# and timestamped run log configured by deepwork.logging_setup.
log = logging.getLogger(__name__)

# Human labels live beside validation so every UI, prompt, event, and status
# consumer displays the same name for a canonical machine key.
_ACCESS_LABELS: dict[str, str] = {
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
    "telegram": "Telegram",
    "steam": "Steam",
}

# SITE_DOMAINS order remains the public picker order, while dict.fromkeys adds
# only app-only keys afterward and removes Discord's duplicate appearance.
# Python guarantees dictionary insertion order:
# https://docs.python.org/3/library/stdtypes.html#dict
_ACCESS_KEYS: tuple[str, ...] = tuple(
    dict.fromkeys((*SITE_DOMAINS, *APP_PROCESSES)),
)


@dataclass(frozen=True, slots=True)
class AccessOption:
    """Describe one canonical checkbox and the policies it can permit."""

    # The frozen dataclass emulates an immutable metadata value that can safely
    # be reused across requests:
    # https://docs.python.org/3/library/dataclasses.html#frozen-instances
    key: str
    label: str
    allows_website: bool
    allows_app: bool

    @property
    def capability_label(self) -> str:
        """Return the compact, human-readable capability badge for Jinja."""

        # Discord is the sole dual-capability option in the current config.
        if self.allows_website and self.allows_app:
            return "Web + App"
        # A SITE_DOMAINS-only key grants hosts-policy access.
        if self.allows_website:
            return "Web"
        # Every remaining option comes from APP_PROCESSES and grants app access.
        return "App"


def _validate_access_catalog() -> None:
    """Fail at import if config keys lack deliberate user-facing metadata."""

    # Config dictionaries are the capability truth; labels must cover their
    # exact union so a new policy cannot silently disappear from the picker.
    configured = set(_ACCESS_KEYS)
    labeled = set(_ACCESS_LABELS)
    if configured != labeled:
        missing = sorted(configured - labeled)
        stale = sorted(labeled - configured)
        raise RuntimeError(
            "Access labels must exactly match SITE_DOMAINS and APP_PROCESSES; "
            f"missing={missing!r}, stale={stale!r}.",
        )


# Validate once before constructing the shared immutable catalog.
_validate_access_catalog()

# Capability booleans are derived from config membership rather than repeated
# policy tables, so Discord automatically becomes one website-and-app option.
_ACCESS_OPTIONS: tuple[AccessOption, ...] = tuple(
    AccessOption(
        key=key,
        label=_ACCESS_LABELS[key],
        allows_website=key in SITE_DOMAINS,
        allows_app=key in APP_PROCESSES,
    )
    for key in _ACCESS_KEYS
)

# Direct keyed lookup keeps label projection simple after normalization.
_OPTIONS_BY_KEY: dict[str, AccessOption] = {
    option.key: option for option in _ACCESS_OPTIONS
}


def access_options() -> tuple[AccessOption, ...]:
    """Return the stable immutable choices shared by all access forms."""

    return _ACCESS_OPTIONS


def normalize_access_keys(values: Iterable[str]) -> tuple[str, ...]:
    """Validate, deduplicate, and policy-order submitted access-group keys."""

    # A set deduplicates repeated checkbox/preset values before stable replay.
    requested: set[str] = set()
    for value in values:
        # Silently stringifying malformed callers could authorize a surprising
        # key, so non-string values fail closed at the shared boundary.
        if not isinstance(value, str):
            raise ValueError("Access group values must be strings.")
        # Forms and hand-edited JSON get forgiving case/whitespace handling.
        key = value.strip().lower()
        # Empty unchecked/optional values have no policy effect.
        if not key:
            continue
        # The config-derived catalog is the server-side allowlist.
        if key not in _OPTIONS_BY_KEY:
            raise ValueError(f"Unknown access group: {key}")
        requested.add(key)
    # Replaying catalog order makes logs, prompts, status, and tests deterministic.
    return tuple(key for key in _ACCESS_KEYS if key in requested)


def access_labels(values: Iterable[str]) -> tuple[str, ...]:
    """Return display labels for validated groups in canonical policy order."""

    return tuple(
        _OPTIONS_BY_KEY[key].label
        for key in normalize_access_keys(values)
    )


def access_site_keys(values: Iterable[str]) -> tuple[str, ...]:
    """Return selected groups that permit a configured website."""

    # Filtering normalized keys preserves the SITE_DOMAINS/catalog order.
    return tuple(
        key
        for key in normalize_access_keys(values)
        if key in SITE_DOMAINS
    )


def access_app_keys(values: Iterable[str]) -> tuple[str, ...]:
    """Return selected groups that permit a configured desktop app."""

    # Discord is retained here as well as by access_site_keys because its one
    # checkbox deliberately grants both capabilities.
    return tuple(
        key
        for key in normalize_access_keys(values)
        if key in APP_PROCESSES
    )


def resolve_work_allowed_groups(
    selected_groups: Iterable[str],
    project: str | None,
    project_allowlists: Mapping[str, Iterable[str]],
) -> tuple[str, ...]:
    """Combine a saved project preset with one-off task access choices."""

    # Normalize one-off choices even when no project preset is selected.
    selected = normalize_access_keys(selected_groups)
    # Empty/whitespace project form values mean "no saved preset."
    project_name = project.strip() if project else None
    preset: tuple[str, ...] = ()
    if project_name:
        # Unknown preset names fail before session state or enforcement changes.
        if project_name not in project_allowlists:
            raise ValueError(f"Unknown project preset: {project_name}")
        preset = normalize_access_keys(project_allowlists[project_name])
    # A final normalization creates one deduplicated canonical union.
    return normalize_access_keys((*preset, *selected))


def _validate_project_allowlists(data: object) -> dict[str, tuple[str, ...]]:
    """Validate decoded projects.json before presets can reach session state."""

    # The established on-disk format is an object mapping names to key arrays.
    if not isinstance(data, dict):
        raise ValueError("projects.json must contain a JSON object.")
    validated: dict[str, tuple[str, ...]] = {}
    for raw_name, raw_groups in data.items():
        # Preset names are user-visible selectors and cannot be empty/non-text.
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValueError("Every project preset needs a non-empty string name.")
        # Retaining JSON arrays preserves compatibility with existing presets.
        if not isinstance(raw_groups, list):
            raise ValueError(
                f"Project preset {raw_name!r} must contain an array of access groups.",
            )
        # Normalize surrounding whitespace without changing meaningful casing.
        name = raw_name.strip()
        # Distinct JSON keys must not collapse onto one trimmed selector name.
        if name in validated:
            raise ValueError(f"Duplicate project preset after trimming: {name}")
        # The same 14-key allowlist validates website and app-only selections.
        validated[name] = normalize_access_keys(raw_groups)
    return validated


def load_project_allowlists(
    path: str | Path = Path("projects.json"),
) -> dict[str, tuple[str, ...]]:
    """Load optional saved project presets, failing early on bad configuration."""

    # pathlib accepts the default and injected test paths uniformly.
    source = Path(path)
    # Missing presets are valid for a fresh clone or user with only ad-hoc tasks.
    if not source.exists():
        return {}
    try:
        # The standard library decoder keeps this small configuration dependency
        # free: https://docs.python.org/3/library/json.html#json.loads
        decoded = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        # Expose a concise configuration error while preserving the cause.
        raise ValueError(f"{source} must contain valid JSON: {exc.msg}") from exc
    except (OSError, UnicodeError) as exc:
        # Filesystem and encoding failures are configuration errors to callers.
        raise ValueError(f"Could not read {source}: {exc}") from exc
    # Validation occurs completely before the returned mapping can reach state.
    validated = _validate_project_allowlists(decoded)
    log.info("project presets loaded: %d from %s", len(validated), source)
    return validated
