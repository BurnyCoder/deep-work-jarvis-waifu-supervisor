# Deep Work — Windows Productivity Enforcement App

Holds you to deep focus on Windows 11: blocks distracting websites, kills
distraction apps, watches your screens + webcam with an AI coach every five
minutes, and speaks encouragement or gentle nudges out loud — all controlled
from a small local web panel.

## Features

1. **Website blocking** — Reddit, YouTube, Twitter/X, Discord, Hacker News,
   LinkedIn, Bluesky, Substack, Facebook, LessWrong, EA Forum and 4chan (plus
   known variants like `old.reddit.com`, `youtu.be`, `x.com`) are redirected
   to `127.0.0.1` via the Windows hosts file, IPv4 and IPv6, inside a fenced
   `# >>> deepwork block` section that is cleanly removed on OFF/exit.
2. **App killing** — a background sweep terminates Discord, Telegram and
   Steam every 3 seconds while enforcement is on.
3. **AI monitoring** — every 5 minutes all monitors and the webcam are
   captured and stitched into one labeled image; every 5 captures one OpenAI
   vision call judges the whole 25-minute window and returns
   `{productive: yes/no, reason: <encouraging sentence>}`.
4. **Spoken feedback** — an LLM writes (and OpenAI TTS speaks) a good-luck
   message when you start a topic, a gentle nudge when you're off track, and
   praise after 30 consecutive productive minutes. Offline `pyttsx3` voice
   available via `TTS_ENGINE=pyttsx3`.
5. **Modes** — **ON** (everything enforced), **OFF** (nothing), **BREAK**
   (timed, auto-restoring; you state what it's for and how long, TTS
   acknowledges). Breaks can allow only specific sites/apps
   (`reddit,discord`) while everything else stays blocked, and come in two
   kinds: *social media* (draws from a **2 h/day allowance**, refused once
   exhausted) or *away from computer*. A `projects.json` file can allowlist
   specific social sites for a named productive project while ON.
6. **Confirmation phrase** — turning enforcement off requires typing exactly
   `I will not stop cool deepwork session`.
7. **Web UI** — `http://127.0.0.1:5599` (port via `UI_PORT`): topic input
   with a dropdown of previous topics, break and disable forms, live status.
8. **Results storage** — `results/captures/*.jpg` (stitched images),
   `results/llm/*.json` (full, uncut LLM request/response pairs),
   `results/sessions/*.jsonl` (timestamped event log), `results/state.json`
   (allowance + topic history, survives restarts). Runtime logs stream to the
   terminal and `logs/deepwork_*.log` simultaneously.

## Requirements

- Windows 11 (hosts file, winsound, UAC elevation are Windows-specific)
- [uv](https://docs.astral.sh/uv/) (Python 3.13 is pinned via `.python-version`)
- An OpenAI API key with access to a vision-capable model and TTS

## Setup

```powershell
git clone <this-repo> deep-work
cd deep-work
uv sync                      # creates ./.venv and installs everything
copy .env.example .env       # then edit .env and set OPENAI_API_KEY
```

All configuration lives in `.env` — see `.env.example` for every variable
(models, intervals, batch size, TTS engine/voice, allowance cap, UI port).

## Run

**Easiest:** double-click **`Start Deep Work.bat`** in Explorer — it asks for
administrator permission once (UAC), starts the app with live logs in a
console window, and opens the control panel in your browser. Closing that
window stops the app and restores the hosts file.

Or from a terminal:

```powershell
uv run pytest                      # unit tests: no admin, no API key, no hardware
uv run python main.py --smoke      # one real capture→vision→speech cycle, then exits
uv run python main.py --dry-hosts  # full app but hosts changes are only logged (no admin)
uv run python main.py              # full app: shows ONE UAC prompt, then the web panel
```

Then open **http://127.0.0.1:5599**, type what you'll work on, press
**Start** — you'll hear your good-luck message and enforcement begins.

### Optional: per-project social allowlist

Create `projects.json` in the repo root, e.g.:

```json
{"ml-research": ["twitter"], "community": ["discord", "bluesky"]}
```

Selecting that project on Start keeps everything blocked *except* those site
groups. Valid group names are the keys of `SITE_DOMAINS` in
`deepwork/config.py` (reddit, youtube, twitter, discord, hackernews,
linkedin, bluesky, substack, facebook, lesswrong, eaforum, 4chan).

## Verifying it works (manual smoke checklist)

1. `uv run python main.py` → accept the UAC prompt.
2. Start a session; check `C:\Windows\System32\drivers\etc\hosts` now has the
   `# >>> deepwork block start` section and `ping reddit.com` answers from
   `127.0.0.1`.
3. Launch Discord or Steam — it dies within ~3 s.
4. Take a 1-minute social break allowing `reddit` — TTS acknowledges, Reddit
   unblocks, and a minute later blocking auto-restores (watch the log).
5. `/disable` with a wrong phrase → refused (403). With the exact phrase →
   everything off and the hosts section removed.
6. Inspect `logs/` and `results/llm/` — every LLM prompt and full response is
   there, untruncated.

## Known limitations & caveats

- **Browser "Secure DNS" (DoH) bypasses hosts blocking.** Disable it in
  Chrome/Edge/Firefox settings (or enforce DoH at the Windows level) or
  blocked sites will still load. Also clear `chrome://net-internals/#dns`
  after toggling. ([background](https://www.howtogeek.com/784196/how-to-edit-the-hosts-file-on-windows-10-or-11/))
- **Windows Defender** may flag hosts edits as
  `SettingsModifier:Win32/HostsFileHijack` — allow the change (it's this app).
- **Per-author `*.substack.com` subdomains** can't be enumerated in a hosts
  file; only `substack.com` itself is blocked.
- **Hard kills skip cleanup.** `atexit` restores the hosts file on normal
  exit/Ctrl+C, but after a hard kill remove the fenced
  `# >>> deepwork block` section from
  `C:\Windows\System32\drivers\etc\hosts` by hand (as admin) and run
  `ipconfig /flushdns`.
- **Model names churn.** `VISION_MODEL`/`TEXT_MODEL`/`TTS_MODEL` are plain
  `.env` strings — check the [OpenAI pricing page](https://developers.openai.com/api/docs/pricing)
  and update when models are retired.
- **Cost**: with `detail: low`, a 5-image analysis costs well under a cent;
  each TTS sentence is similarly cheap. Everything runs on the mini tier by
  default.

## Development

See `AGENTS.md` for architecture, module map, conventions (TDD, dependency
injection, source-linked comments) and gotchas. Tests: `uv run pytest`.
