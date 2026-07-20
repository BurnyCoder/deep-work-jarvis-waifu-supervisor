# Tests for deepwork/site_access.py — the shared policy boundary that turns
# browser form values and projects.json presets into known SITE_DOMAINS keys.
# The tests follow OWASP's server-side allowlist guidance:
# https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html

import json

import pytest

from deepwork.site_access import (
    load_project_allowlists,
    normalize_site_keys,
    resolve_work_allowed_sites,
    site_labels,
    site_options,
)


def test_site_options_cover_every_blocked_group_with_readable_labels():
    # One central option list keeps the HTML form and validation policy in sync.
    options = site_options()
    assert options[0] == ("reddit", "Reddit")
    assert ("twitter", "X / Twitter") in options
    assert ("hackernews", "Hacker News") in options
    assert ("eaforum", "EA Forum") in options
    assert len(options) == 12


def test_normalize_site_keys_deduplicates_in_config_order():
    # Submission order must not make status/log output fluctuate between runs.
    assert normalize_site_keys(["linkedin", "twitter", "linkedin"]) == (
        "twitter",
        "linkedin",
    )


def test_site_labels_reuse_the_policy_owned_human_names():
    assert site_labels(["linkedin", "twitter"]) == ("X / Twitter", "LinkedIn")


def test_normalize_site_keys_rejects_unknown_values():
    # Client-side checkboxes are not a security boundary; forged keys fail.
    with pytest.raises(ValueError, match="Unknown website group"):
        normalize_site_keys(["twitter", "not-a-real-site"])


def test_project_and_one_off_sites_are_combined_without_duplicates():
    presets = {"ml-research": ("twitter", "youtube")}
    assert resolve_work_allowed_sites(
        selected_sites=["linkedin", "twitter"],
        project="ml-research",
        project_allowlists=presets,
    ) == ("youtube", "twitter", "linkedin")


def test_unknown_project_is_rejected():
    with pytest.raises(ValueError, match="Unknown project preset"):
        resolve_work_allowed_sites(
            selected_sites=[],
            project="missing",
            project_allowlists={"known": ("twitter",)},
        )


def test_load_project_allowlists_validates_and_normalizes_json(tmp_path):
    path = tmp_path / "projects.json"
    path.write_text(
        json.dumps({"ml-research": ["linkedin", "twitter", "twitter"]}),
        encoding="utf-8",
    )
    assert load_project_allowlists(path) == {
        "ml-research": ("twitter", "linkedin"),
    }


@pytest.mark.parametrize(
    "payload, message",
    [
        ("[]", "JSON object"),
        ('{"work": "twitter"}', "array of website groups"),
        ('{"work": ["unknown"]}', "Unknown website group"),
        ("{broken", "valid JSON"),
    ],
)
def test_load_project_allowlists_fails_fast_on_bad_configuration(
    tmp_path,
    payload,
    message,
):
    path = tmp_path / "projects.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_project_allowlists(path)
