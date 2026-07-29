# Tests for the unified website-and-app access-policy boundary. Global context:
# forms, state, enforcement, prompts, status, and project presets must share one
# canonical vocabulary instead of independently interpreting site and app keys.
# Forged browser values are covered because OWASP requires server-side allowlist
# validation: https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html

import json
from dataclasses import FrozenInstanceError

import pytest

from deepwork.access_policy import (
    AccessOption,
    access_app_keys,
    access_labels,
    access_options,
    access_site_keys,
    load_project_allowlists,
    normalize_access_keys,
    resolve_work_allowed_groups,
)
from deepwork.config import APP_PROCESSES, SITE_DOMAINS


def test_access_options_cover_config_union_in_stable_policy_order():
    """The shared picker must expose every configured site or app exactly once."""

    options = access_options()
    # Python dictionaries preserve insertion order, making configuration order
    # a stable public contract: https://docs.python.org/3/library/stdtypes.html#dict
    assert tuple(option.key for option in options) == (
        *SITE_DOMAINS,
        "telegram",
        "steam",
    )
    assert len(options) == 14
    assert {option.key for option in options} == set(SITE_DOMAINS) | set(APP_PROCESSES)


def test_access_options_describe_website_app_and_combined_capabilities():
    """Jinja receives both machine-readable booleans and a readable badge label."""

    by_key = {option.key: option for option in access_options()}
    assert by_key["twitter"] == AccessOption(
        key="twitter",
        label="X / Twitter",
        allows_website=True,
        allows_app=False,
    )
    assert by_key["telegram"] == AccessOption(
        key="telegram",
        label="Telegram",
        allows_website=False,
        allows_app=True,
    )
    assert by_key["discord"] == AccessOption(
        key="discord",
        label="Discord",
        allows_website=True,
        allows_app=True,
    )
    assert by_key["twitter"].capability_label == "Web"
    assert by_key["telegram"].capability_label == "App"
    assert by_key["discord"].capability_label == "Web + App"


def test_access_option_is_frozen():
    """Policy metadata must be safe to share without a mutable global registry."""

    option = access_options()[0]
    # frozen=True emulates read-only instances:
    # https://docs.python.org/3/library/dataclasses.html#frozen-instances
    with pytest.raises(FrozenInstanceError):
        option.label = "Changed"


def test_normalize_access_keys_deduplicates_in_policy_order():
    """Submission order must not make logs, prompts, or status fluctuate."""

    assert normalize_access_keys(
        ["steam", "linkedin", "discord", "telegram", "linkedin"],
    ) == ("discord", "linkedin", "telegram", "steam")


def test_access_labels_reuse_policy_owned_human_names():
    """Every display consumer gets the same normalized labels."""

    assert access_labels(["steam", "twitter", "discord"]) == (
        "X / Twitter",
        "Discord",
        "Steam",
    )


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (["twitter", "not-a-real-option"], "Unknown access group"),
        (["twitter", 7], "Access group values must be strings"),
    ],
)
def test_normalize_access_keys_rejects_invalid_values(values, message):
    """Malformed programmatic callers and forged form values fail closed."""

    with pytest.raises(ValueError, match=message):
        normalize_access_keys(values)


def test_access_site_and_app_keys_derive_capabilities_from_one_selection():
    """Discord expands to both policies while app-only and web-only keys do not."""

    selected = ["telegram", "twitter", "discord", "steam"]
    assert access_site_keys(selected) == ("twitter", "discord")
    assert access_app_keys(selected) == ("discord", "telegram", "steam")


def test_project_and_one_off_groups_are_combined_without_duplicates():
    """Saved presets and one-off choices use the same 14-key policy."""

    presets = {"ml-research": ("twitter", "telegram", "youtube")}
    assert resolve_work_allowed_groups(
        selected_groups=["linkedin", "telegram", "discord"],
        project="ml-research",
        project_allowlists=presets,
    ) == ("youtube", "twitter", "discord", "linkedin", "telegram")


def test_unknown_project_is_rejected():
    """A typo must not silently create a weaker session policy."""

    with pytest.raises(ValueError, match="Unknown project preset"):
        resolve_work_allowed_groups(
            selected_groups=[],
            project="missing",
            project_allowlists={"known": ("twitter",)},
        )


def test_load_project_allowlists_accepts_apps_and_normalizes_json(tmp_path):
    """The existing JSON-array format now accepts both site and app-only keys."""

    path = tmp_path / "projects.json"
    # json.dumps produces a standards-compliant fixture using the same standard
    # library used by production: https://docs.python.org/3/library/json.html
    path.write_text(
        json.dumps(
            {
                "ml-research": [
                    "steam",
                    "linkedin",
                    "telegram",
                    "twitter",
                    "telegram",
                ],
            },
        ),
        encoding="utf-8",
    )
    assert load_project_allowlists(path) == {
        "ml-research": ("twitter", "linkedin", "telegram", "steam"),
    }


def test_load_project_allowlists_returns_empty_mapping_when_file_is_absent(tmp_path):
    """Project presets remain optional for a fresh clone."""

    assert load_project_allowlists(tmp_path / "missing.json") == {}


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("[]", "JSON object"),
        ('{"work": "twitter"}', "array of access groups"),
        ('{"work": ["unknown"]}', "Unknown access group"),
        ('{"work": [1]}', "Access group values must be strings"),
        ("{broken", "valid JSON"),
    ],
)
def test_load_project_allowlists_fails_fast_on_bad_configuration(
    tmp_path,
    payload,
    message,
):
    """Invalid configuration fails before it can mutate session policy."""

    path = tmp_path / "projects.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_project_allowlists(path)
