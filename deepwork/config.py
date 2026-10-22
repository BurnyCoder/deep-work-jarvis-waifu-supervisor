# Central configuration for the deep-work app.
# Global context: startup builds settings here, then injects settings or their
# individual values into collaborators. Tests can pass a plain environment
# mapping to load_config without loading a local credential file.
# dotenv usage: https://pypi.org/project/python-dotenv/

# frozen dataclasses reject ordinary field assignment; annotations describe types
# but do not validate them at runtime:
# https://docs.python.org/3/library/dataclasses.html#frozen-instances
from dataclasses import dataclass, field
# Mapping is the loosest read-only dict type for the env parameter:
# https://docs.python.org/3/library/typing.html#typing.Mapping
from typing import Mapping

# Startup calls load_dotenv() explicitly; its default search walks upward from
# the calling source file and existing environment values win:
# https://bbc2.github.io/python-dotenv/#getting-started
from dotenv import load_dotenv

# The exact phrase the user must type to turn enforcement OFF (requirement 6):
# friction against impulsive disabling while distracted.
CONFIRMATION_PHRASE = "I will not stop cool deepwork session"

# Default path used by this app for a Windows installation under C:\Windows;
# Windows itself locates hosts under its installation directory:
# https://learn.microsoft.com/en-us/troubleshoot/windows-client/networking/troubleshoot-dns-client-resolution-issues
HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"

# Site groups: human-readable name -> explicit domain variants.
# These are explicit hostname mappings, not a complete inventory of each service.
# System-resolver behavior: https://learn.microsoft.com/en-us/troubleshoot/windows-client/networking/troubleshoot-dns-client-resolution-issues
# Names are the handles used by break allowances ("allow only reddit").
SITE_DOMAINS: dict[str, list[str]] = {
    "reddit": ["reddit.com", "old.reddit.com", "np.reddit.com", "i.redd.it", "v.redd.it"],
    "youtube": ["youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"],
    "twitter": ["twitter.com", "mobile.twitter.com", "x.com", "t.co"],
    "discord": ["discord.com", "discord.gg", "discordapp.com"],
    "hackernews": ["news.ycombinator.com"],
    "linkedin": ["linkedin.com"],
    "bluesky": ["bsky.app"],
    # Author subdomains are not enumerated in this catalog; see README's
    # explicit-hostname limitation before relying on Substack blocking.
    "substack": ["substack.com"],
    "facebook": ["facebook.com", "m.facebook.com", "fb.com"],
    "lesswrong": ["lesswrong.com", "greaterwrong.com"],
    "eaforum": ["forum.effectivealtruism.org"],
    "4chan": ["4chan.org", "boards.4chan.org", "4channel.org", "boards.4channel.org"],
}

# App groups: human name -> process executable names psutil will match
# case-insensitively. Including Steam's web helper is an explicit local policy;
# this list does not establish which processes are running on a particular PC.
APP_PROCESSES: dict[str, list[str]] = {
    "discord": ["discord.exe"],
    "telegram": ["telegram.exe"],
    "steam": ["steam.exe", "steamwebhelper.exe"],
}


def expand_www(domains: list[str]) -> list[str]:
    # Add a www alias for this catalog's one-dot hostnames. This is a local
    # heuristic, not a general registered-domain parser (consider example.co.uk):
    # https://publicsuffix.org/learn/
    out: list[str] = []
    for d in domains:
        out.append(d)                       # keep the original entry
        if d.count(".") == 1:               # apex heuristic: one dot only
            out.append(f"www.{d}")          # f-string join, PEP 498
    return out


def all_blocked_domains() -> tuple[str, ...]:
    # Flatten every site group through expand_www into one deduplicated,
    # order-stable tuple (dict.fromkeys preserves insertion order — idiom from
    # https://docs.python.org/3/library/stdtypes.html#dict.fromkeys).
    flat = [d for domains in SITE_DOMAINS.values() for d in expand_www(domains)]
    return tuple(dict.fromkeys(flat))


@dataclass(frozen=True)
class Config:
    # The intended str/int/tuple values need no mutation during a run. Frozen
    # only prevents ordinary field assignment; it is not general synchronization:
    # https://docs.python.org/3.13/library/dataclasses.html#frozen-instances
    openai_api_key: str
    # Every text/image Responses workload defaults to the cost-sensitive
    # GPT-6 Luna tier at medium, OpenAI's documented default; keeping
    # each field separate still lets .env tune one workload independently:
    # https://developers.openai.com/api/docs/models/gpt-6-luna
    vision_model: str = "gpt-6-luna"
    progress_reasoning_effort: str = "medium"
    agent_vision_model: str = "gpt-6-luna"
    agent_reasoning_effort: str = "medium"
    text_model: str = "gpt-6-luna"
    text_reasoning_effort: str = "medium"
    # Speech remains on an audio-output model because Luna outputs text only:
    # https://developers.openai.com/api/docs/models/gpt-6-luna
    tts_engine: str = "openai"               # "openai" | "pyttsx3" fallback
    tts_model: str = "gpt-4o-mini-tts"       # https://developers.openai.com/api/docs/guides/text-to-speech
    tts_voice: str = "coral"                 # one of the 13 built-in voices
    capture_interval_s: int = 300            # delay after each completed tick
    progress_window_captures: int = 5        # max history, min 2 for comparison
    kill_interval_s: int = 3                 # app-kill sweep period (seconds)
    agent_check_interval_s: int = 60         # agentic mode: AI-agent activity poll
    daily_social_cap_min: int = 120          # requirement 5: 2 h/day cap
    ui_port: int = 5000                      # Flask default port
    hosts_path: str = HOSTS_PATH
    confirmation_phrase: str = CONFIRMATION_PHRASE
    # Recompute catalog-derived tuples for each Config; tuples themselves are
    # immutable and do not require a factory to avoid mutable defaults:
    # https://docs.python.org/3.13/library/dataclasses.html#default-factory-functions
    blocked_domains: tuple[str, ...] = field(default_factory=all_blocked_domains)
    kill_processes: tuple[str, ...] = field(
        default_factory=lambda: tuple(p for procs in APP_PROCESSES.values() for p in procs)
    )


def load_config(env: Mapping[str, str]) -> Config:
    # Build a Config from any mapping (os.environ in prod, a dict in tests).
    # .get(key, default) keeps each line one readable lookup.
    return Config(
        openai_api_key=env.get("OPENAI_API_KEY", ""),
        vision_model=env.get("VISION_MODEL", Config.vision_model),
        progress_reasoning_effort=env.get(
            "PROGRESS_REASONING_EFFORT",
            Config.progress_reasoning_effort,
        ),
        agent_vision_model=env.get(
            "AGENT_VISION_MODEL",
            Config.agent_vision_model,
        ),
        agent_reasoning_effort=env.get(
            "AGENT_REASONING_EFFORT",
            Config.agent_reasoning_effort,
        ),
        text_model=env.get("TEXT_MODEL", Config.text_model),
        text_reasoning_effort=env.get(
            "TEXT_REASONING_EFFORT",
            Config.text_reasoning_effort,
        ),
        tts_engine=env.get("TTS_ENGINE", Config.tts_engine),
        tts_model=env.get("TTS_MODEL", Config.tts_model),
        tts_voice=env.get("TTS_VOICE", Config.tts_voice),
        # int() parses the .env string form; defaults are already ints.
        capture_interval_s=int(env.get("CAPTURE_INTERVAL_S", Config.capture_interval_s)),
        # BATCH_SIZE is a compatibility fallback for existing local .env
        # files; new installs use the name matching rolling-window semantics.
        progress_window_captures=int(
            env.get("PROGRESS_WINDOW_CAPTURES",
                    env.get("BATCH_SIZE", Config.progress_window_captures))
        ),
        kill_interval_s=int(env.get("KILL_INTERVAL_S", Config.kill_interval_s)),
        agent_check_interval_s=int(env.get("AGENT_CHECK_INTERVAL_S", Config.agent_check_interval_s)),
        daily_social_cap_min=int(env.get("DAILY_SOCIAL_CAP_MIN", Config.daily_social_cap_min)),
        ui_port=int(env.get("UI_PORT", Config.ui_port)),
    )


def load_config_from_dotenv() -> Config:
    # Production entry point: pull .env into os.environ, then read it.
    # Import os here to keep the module's test path free of os.environ.
    import os
    load_dotenv()                            # search upward; do not override env
    return load_config(os.environ)
