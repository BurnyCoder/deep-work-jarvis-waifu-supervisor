# Tests for deepwork/config.py — written FIRST (TDD) to pin down the Config
# contract before implementation. Run with `uv run pytest`.
# pytest basics: https://docs.pytest.org/en/stable/getting-started.html

from deepwork.config import SITE_DOMAINS, expand_www, load_config


def test_defaults_when_env_empty():
    # load_config takes an explicit mapping (not os.environ) so tests are
    # hermetic — dependency-injection pattern from
    # https://docs.pytest.org/en/stable/how-to/monkeypatch.html
    cfg = load_config({"OPENAI_API_KEY": "sk-test"})
    assert cfg.openai_api_key == "sk-test"
    assert cfg.vision_model == "gpt-5.6-luna"
    assert cfg.progress_reasoning_effort == "xhigh"
    assert cfg.agent_vision_model == "gpt-5.6-luna"
    assert cfg.agent_reasoning_effort == "xhigh"
    assert cfg.text_model == "gpt-5.6-luna"
    assert cfg.text_reasoning_effort == "xhigh"
    assert cfg.capture_interval_s == 300          # 5-minute default cadence
    assert cfg.progress_window_captures == 5      # maximum comparison history
    assert cfg.kill_interval_s == 3               # app-kill sweep period
    assert cfg.daily_social_cap_min == 120        # 2 h/day social allowance
    assert cfg.ui_port == 5000
    assert cfg.tts_engine == "openai"             # user-chosen default voice
    assert cfg.confirmation_phrase == "I will not stop cool deepwork session"


def test_env_overrides_win():
    # Every tunable must be overridable from .env (project requirement:
    # "Use .env for config") — ints are parsed from their string form.
    cfg = load_config({
        "OPENAI_API_KEY": "sk-test",
        "VISION_MODEL": "some-model",
        "PROGRESS_REASONING_EFFORT": "high",
        "AGENT_VISION_MODEL": "agent-model",
        "AGENT_REASONING_EFFORT": "medium",
        "TEXT_MODEL": "text-model",
        "TEXT_REASONING_EFFORT": "low",
        "CAPTURE_INTERVAL_S": "60",
        "PROGRESS_WINDOW_CAPTURES": "2",
        "TTS_ENGINE": "pyttsx3",
        "UI_PORT": "8080",
    })
    assert cfg.vision_model == "some-model"
    assert cfg.progress_reasoning_effort == "high"
    assert cfg.agent_vision_model == "agent-model"
    assert cfg.agent_reasoning_effort == "medium"
    assert cfg.text_model == "text-model"
    assert cfg.text_reasoning_effort == "low"
    assert cfg.capture_interval_s == 60
    assert cfg.progress_window_captures == 2
    assert cfg.tts_engine == "pyttsx3"
    assert cfg.ui_port == 8080


def test_legacy_batch_size_still_configures_progress_window():
    # Existing local .env files used BATCH_SIZE before the analyzer changed
    # from non-overlapping batches to a rolling progress window.
    cfg = load_config({"OPENAI_API_KEY": "sk-test", "BATCH_SIZE": "3"})
    assert cfg.progress_window_captures == 3


def test_blocklist_covers_required_sites_and_variants():
    # The spec's 12 site groups must all be present, including known
    # subdomain/alias variants that a hosts file needs listed explicitly
    # (hosts files have no wildcards: https://www.currentware.com/blog/how-to-block-websites-using-hosts-file/)
    domains = set(load_config({"OPENAI_API_KEY": "k"}).blocked_domains)
    for required in [
        "reddit.com", "www.reddit.com", "old.reddit.com",
        "youtube.com", "youtu.be", "m.youtube.com",
        "twitter.com", "x.com",
        "discord.com", "discord.gg",
        "news.ycombinator.com",
        "linkedin.com",
        "bsky.app",
        "substack.com",
        "facebook.com", "fb.com",
        "lesswrong.com", "greaterwrong.com",
        "forum.effectivealtruism.org",
        "4chan.org", "boards.4chan.org", "4channel.org",
    ]:
        assert required in domains, f"missing {required}"


def test_site_groups_map_names_to_domains():
    # SITE_DOMAINS keys are the human names used by break allowances
    # ("allow only reddit during this break") — each maps to >= 1 domain.
    assert "reddit" in SITE_DOMAINS and "youtube" in SITE_DOMAINS
    assert all(len(v) >= 1 for v in SITE_DOMAINS.values())


def test_expand_www_adds_www_only_to_apex_domains():
    # www. prefix is added for apex domains (one dot) but not for domains
    # that already carry a subdomain — avoids nonsense like www.old.reddit.com
    assert expand_www(["reddit.com"]) == ["reddit.com", "www.reddit.com"]
    assert expand_www(["old.reddit.com"]) == ["old.reddit.com"]


def test_kill_processes_cover_spec_apps():
    # Requirement 2: continuously kill Discord, Telegram, Steam.
    procs = set(load_config({"OPENAI_API_KEY": "k"}).kill_processes)
    assert {"discord.exe", "telegram.exe", "steam.exe"} <= procs
