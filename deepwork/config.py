# Central configuration for the deep-work app.
# Global context: every other module receives a frozen Config object built
# here from .env (python-dotenv) — no module reads os.environ directly, so
# tests can inject a plain dict instead (dependency injection).
# dotenv usage: https://pypi.org/project/python-dotenv/

# dataclasses give an immutable, typed settings record without boilerplate:
# https://docs.python.org/3/library/dataclasses.html#frozen-instances
from dataclasses import dataclass, field
# Mapping is the loosest read-only dict type for the env parameter:
# https://docs.python.org/3/library/typing.html#typing.Mapping
from typing import Mapping

# load_dotenv() copies KEY=VALUE lines from ./.env into os.environ once at
# import time of the caller (main.py) — https://pypi.org/project/python-dotenv/
from dotenv import load_dotenv

# The exact phrase the user must type to turn enforcement OFF (requirement 6):
# friction against impulsive disabling while distracted.
CONFIRMATION_PHRASE = "I will not stop cool deepwork session"

# Windows hosts file location — fixed since Windows NT:
# https://learn.microsoft.com/en-us/troubleshoot/windows-server/networking/microsoft-tcp-ip-host-name-resolution-order
HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"

# Site groups: human-readable name -> explicit domain variants.
# Hosts files have NO wildcard support, so every subdomain a browser might
# hit must be listed (https://www.currentware.com/blog/how-to-block-websites-using-hosts-file/).
# Names are the handles used by break allowances ("allow only reddit").
SITE_DOMAINS: dict[str, list[str]] = {
    "reddit": ["reddit.com", "old.reddit.com", "np.reddit.com", "i.redd.it", "v.redd.it"],
    "youtube": ["youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"],
    "twitter": ["twitter.com", "mobile.twitter.com", "x.com", "t.co"],
    "discord": ["discord.com", "discord.gg", "discordapp.com"],
    "hackernews": ["news.ycombinator.com"],
    "linkedin": ["linkedin.com"],
    "bluesky": ["bsky.app"],
    # Per-author *.substack.com subdomains cannot be enumerated — known
    # limitation documented in README.
    "substack": ["substack.com"],
    "facebook": ["facebook.com", "m.facebook.com", "fb.com"],
    "lesswrong": ["lesswrong.com", "greaterwrong.com"],
    "eaforum": ["forum.effectivealtruism.org"],
    "4chan": ["4chan.org", "boards.4chan.org", "4channel.org", "boards.4channel.org"],
}

# Site groups that count as "social media" for the 2 h/day allowance
# (requirement 5) — HN/LessWrong/EA Forum are distracting but the spec's
# allowance language targets social media; keep the full blocklist for ON mode.
SOCIAL_SITES = {"reddit", "youtube", "twitter", "discord", "bluesky", "facebook", "4chan"}

# App groups: human name -> process executable names psutil will match
# case-insensitively. steamwebhelper.exe is Steam's always-running CEF child:
# https://help.steampowered.com/en/faqs/view/1C48-3777-0596-234B
APP_PROCESSES: dict[str, list[str]] = {
    "discord": ["discord.exe"],
    "telegram": ["telegram.exe"],
    "steam": ["steam.exe", "steamwebhelper.exe"],
}


def expand_www(domains: list[str]) -> list[str]:
    # Browsers try both apex and www forms, so hosts entries need both
    # (https://www.howtogeek.com/784196/how-to-edit-the-hosts-file-on-windows-10-or-11/).
    # A domain with exactly one dot is an apex (reddit.com) — add its www
    # twin; deeper names (old.reddit.com) already pin a subdomain.
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
    # Frozen dataclass = read-only after construction, safe to share across
    # threads without locks (https://docs.python.org/3/library/dataclasses.html).
    openai_api_key: str
    # Every text/image Responses workload defaults to GPT-5.6 Sol at xhigh;
    # keeping each field separate still lets .env tune one workload without
    # silently changing the others:
    # https://developers.openai.com/api/docs/guides/latest-model
    vision_model: str = "gpt-5.6-sol"
    progress_reasoning_effort: str = "xhigh"
    agent_vision_model: str = "gpt-5.6-sol"
    agent_reasoning_effort: str = "xhigh"
    text_model: str = "gpt-5.6-sol"
    text_reasoning_effort: str = "xhigh"
    # Speech remains on an audio-output model because Sol outputs text only:
    # https://developers.openai.com/api/docs/models/gpt-5.6-sol
    tts_engine: str = "openai"               # "openai" | "pyttsx3" fallback
    tts_model: str = "gpt-4o-mini-tts"       # https://developers.openai.com/api/docs/guides/text-to-speech
    tts_voice: str = "coral"                 # one of the 13 built-in voices
    capture_interval_s: int = 300            # requirement 3: every 5 minutes
    progress_window_captures: int = 5        # last 25 min at default cadence
    kill_interval_s: int = 3                 # app-kill sweep period (seconds)
    agent_check_interval_s: int = 60         # agentic mode: AI-agent activity poll
    daily_social_cap_min: int = 120          # requirement 5: 2 h/day cap
    ui_port: int = 5000                      # Flask default port
    hosts_path: str = HOSTS_PATH
    confirmation_phrase: str = CONFIRMATION_PHRASE
    # default_factory because tuples from a function call are mutable-default
    # territory: https://docs.python.org/3/library/dataclasses.html#default-factory-functions
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
    load_dotenv()                            # no-op if .env is absent
    return load_config(os.environ)
