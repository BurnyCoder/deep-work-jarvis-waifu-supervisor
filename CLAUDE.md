## What this is

A Windows 11 productivity enforcement app: hosts-file website blocking,
distraction-app killing, periodic AI screen/webcam monitoring with OpenAI
vision, spoken LLM-generated feedback, ON/OFF/BREAK modes with a daily
social-media allowance, a confirmation-phrase gate, a local Flask control
panel, and results storage. Python 3.13, uv-managed local `.venv`.

## Commands

```powershell
uv sync                          # install deps into ./.venv
uv run pytest                    # full unit suite (no admin, no API key, no hardware)
uv run python main.py            # full app: UAC elevation + hosts writes + web UI
uv run python main.py --dry-hosts  # full app, hosts writes only logged (no admin)
uv run python main.py --smoke    # one real capture→vision→TTS cycle, then exit
```

`Start Deep Work.bat` (repo root) is the double-click launcher: self-elevates
via UAC, checks uv exists, opens the browser panel, runs `uv run python main.py`.

## Architecture (wrapper → phases → modules)

`main.py` is a table of contents: elevation → config+logging → blocker
selection → object wiring → atexit safety → run. All logic lives in
`deepwork/`:

| Module | Responsibility |
|---|---|
| `config.py` | `.env` → frozen `Config`; site/app group tables (`SITE_DOMAINS`, `APP_PROCESSES`) |
| `logging_setup.py` | root logger → timestamped file in `logs/` + terminal, utf-8 |
| `state.py` | thread-safe `SessionState`: modes, breaks, 2h/day social allowance, `effective_blocklist()`, phrase gate |
| `storage.py` | `results/` writers: capture JPEGs, uncut LLM JSON, session JSONL, `state.json` |
| `scheduler.py` | enforcer thread (kill sweep + break watchdog) and monitor thread (capture→analyze→speak) |
| `blocking/admin.py` | `IsUserAnAdmin` check + `ShellExecuteW("runas")` self-relaunch |
| `blocking/hosts_blocker.py` | marker-fenced idempotent hosts edits + `ipconfig /flushdns`; `DryRunBlocker` for dev |
| `blocking/app_killer.py` | psutil sweep killing target process names |
| `monitoring/screen_capture.py` | mss per-monitor grabs → PIL |
| `monitoring/webcam_capture.py` | OpenCV `CAP_DSHOW` single frame, non-fatal on failure |
| `monitoring/stitcher.py` | labeled vertical composite of all captures |
| `monitoring/analyzer.py` | batch of N captures → `responses.parse` → `ProductivityVerdict` |
| `feedback/messages.py` | LLM-written good-luck / nudge / praise / break-ack sentences |
| `feedback/tts.py` | OpenAI TTS→WAV→winsound or pyttsx3; single `SpeechQueue` worker |
| `webui/app.py` | Flask factory: `/`, `/start`, `/break`, `/disable`, `/status` |

## Conventions

- **TDD**: every module has a test file in `tests/`; hardware and network are
  faked (see `FakeClient`, `FakeBlocker`, `capture_fn` injection patterns).
- **Dependency injection everywhere**: paths, clients, clocks (`now=`), and
  callables are constructor/method parameters — never patched globals.
- **Comments cite sources**: non-obvious lines link the doc/guide they came
  from; keep that up when editing.
- **Feature branches**: work on `feat/<name>`, merge to `master` with
  `--no-ff`; one meaningful unit per commit.
- **Secrets**: `.env` is gitignored and must never be committed; `.env.example`
  documents every variable.
- **Full LLM logging**: every prompt and output is logged uncut to `logs/`
  and persisted as JSON under `results/llm/` — preserve this invariant.

## Gotchas

- Port 5000 can be shadowed by `wslrelay` on Windows — `UI_PORT` lives in `.env`.
- opencv-python wheels for Python 3.14 are unreliable; `.python-version` pins 3.13.
- pyttsx3 engines are re-created per utterance (reuse bug nateshmbhat/pyttsx3#193).
- Browser "Secure DNS" (DoH) bypasses hosts blocking — see README caveats.
- `SessionState` methods take `now: datetime` for testability; pass it in new code.

# Deep Work: Windows Productivity Enforcement App

Holds you to deep focus on Windows 11: blocks distracting websites, kills
distraction apps, watches your screens + webcam with an AI coach every five
minutes, and speaks encouragement or gentle nudges out loud, all controlled
from a small local web panel.

<img width="1278" height="1051" alt="image" src="https://github.com/user-attachments/assets/348fd037-84b0-422a-9c74-cbf41163c0d2" />

## Features

1. **Website blocking**: Reddit, YouTube, Twitter/X, Discord, Hacker News,
   LinkedIn, Bluesky, Substack, Facebook, LessWrong, EA Forum and 4chan (plus
   known variants like `old.reddit.com`, `youtu.be`, `x.com`) are redirected
   to `127.0.0.1` via the Windows hosts file, IPv4 and IPv6, inside a fenced
   `# >>> deepwork block` section that is cleanly removed on OFF/exit.
2. **App killing**: a background sweep terminates Discord, Telegram and
   Steam every 3 seconds while enforcement is on.
3. **AI monitoring**: every 5 minutes all monitors and the webcam are
   captured and stitched into one labeled image; every 5 captures one OpenAI
   vision call judges the whole 25-minute window and returns
   `{productive: yes/no, reason: <encouraging sentence>}`.
4. **Spoken feedback**: an LLM writes (and OpenAI TTS speaks) a good-luck
   message when you start a topic, a gentle nudge when you're off track, and
   praise after 30 consecutive productive minutes. Offline `pyttsx3` voice
   available via `TTS_ENGINE=pyttsx3`.
5. **Modes**: **ON** (everything enforced), **OFF** (nothing), **BREAK**
   (timed, auto-restoring; you state what it's for and how long, TTS
   acknowledges). Breaks can allow only specific sites/apps
   (`reddit,discord`) while everything else stays blocked, and come in two
   kinds: *social media* (draws from a **2 h/day allowance**, refused once
   exhausted) or *away from computer*. A `projects.json` file can allowlist
   specific social sites for a named productive project while ON.
6. **Confirmation phrase** : turning enforcement off requires typing exactly
   `I will not stop cool deepwork session`.
7. **Web UI**: `http://127.0.0.1:5599` (port via `UI_PORT`): topic input
   with a dropdown of previous topics, break and disable forms, live status.
8. **Results storage**: `results/captures/*.jpg` (stitched images),
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

All configuration lives in `.env`: see `.env.example` for every variable
(models, intervals, batch size, TTS engine/voice, allowance cap, UI port).

## Run

**Easiest:** double-click **`Start Deep Work.bat`** in Explorer: it asks for
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
**Start**: you'll hear your good-luck message and enforcement begins.

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
3. Launch Discord or Steam: it dies within ~3 s.
4. Take a 1-minute social break allowing `reddit`: TTS acknowledges, Reddit
   unblocks, and a minute later blocking auto-restores (watch the log).
5. `/disable` with a wrong phrase → refused (403). With the exact phrase →
   everything off and the hosts section removed.
6. Inspect `logs/` and `results/llm/`: every LLM prompt and full response is
   there, untruncated.

## Known limitations & caveats

- **Browser "Secure DNS" (DoH) bypasses hosts blocking.** Disable it in
  Chrome/Edge/Firefox settings (or enforce DoH at the Windows level) or
  blocked sites will still load. Also clear `chrome://net-internals/#dns`
  after toggling. ([background](https://www.howtogeek.com/784196/how-to-edit-the-hosts-file-on-windows-10-or-11/))
- **Windows Defender** may flag hosts edits as
  `SettingsModifier:Win32/HostsFileHijack`: allow the change (it's this app).
- **Per-author `*.substack.com` subdomains** can't be enumerated in a hosts
  file; only `substack.com` itself is blocked.
- **Hard kills skip cleanup.** `atexit` restores the hosts file on normal
  exit/Ctrl+C, but after a hard kill remove the fenced
  `# >>> deepwork block` section from
  `C:\Windows\System32\drivers\etc\hosts` by hand (as admin) and run
  `ipconfig /flushdns`.
- **Model names churn.** `VISION_MODEL`/`TEXT_MODEL`/`TTS_MODEL` are plain
  `.env` strings: check the [OpenAI pricing page](https://developers.openai.com/api/docs/pricing)
  and update when models are retired.
- **Cost**: with `detail: low`, a 5-image analysis costs well under a cent;
  each TTS sentence is similarly cheap. Everything runs on the mini tier by
  default.

## Development

See `AGENTS.md` for architecture, module map, conventions (TDD, dependency
injection, source-linked comments) and gotchas. Tests: `uv run pytest`.

# Rules to follow

Make the simplest possible actually practically functioning implementations of new features as a starter, not just demos. 

When figuring out a solution, search the web on how others do it and how to do it, including docs.

The code should be modular and functions/classes abstract with implementation details hidden as you go deeper, split it into files, there should be one abstracted wrapper file that calls different clearly named readable phases as imported modular functions.

Split it into modular files and directories as complexity grows.

Do not duplicate code, use reusable functions for various features, and call them, when possible.

Add comprehensible timestamped logging, make sure all prompts and outputs are written to timestamped logs file and terminal realtime.

Add comments to each file, function and line of code with local explanation and global context sections. Actually explain how the line does it. Don't generate them using scripts, edit each line using file edit tool. Search the web for context.

Make sure as many lines of code as possible are grounded in some library docs, guides on the internet, github repos, programming language docs, etc., and source link them in comments. Make sure to double-check the accuracy of your code while implementing code from these sources to minimize hallucinations.

Use .env for config.

Use uv.

Use local venv in this folder.

Use the current working directory.

Make sure all important details are in README.md.

Make sure README.md and AGENTS.md AND CLAUDE.md is updated according to the codebase.

Initiate git project but dont create github repo on my github account yet.

Make sure that the github repo includes all information to make it replicable for anyone cloning the repo. How to install and setup everything included in README.md.

Split commits into meaningful functional units.

Create new branches, pull requests, and merges, for features, on your own, instead of the user.

Do test driven development.

When testing, run the whole pipeline like a user would. Make sure to inspect logs and fix issues if you find any in the logs or overall. Keep running and fixing until it all works flawlessly in logs and the output makes sense. Outputs from LLMs should correspond to README descriptions, and to prompts in code. After each fix, push it to github, run, repeat, look for fixes, fix, repeat, continue until it all works flawlessly in logs and the output makes sense. 

Make sure all prompts and outputs from LLMs are written into logs without being cut off. 

Before writing anything, ask yourself:
- does it need to exist, 
- does standard library or some library or github repo already do it
- can it be simpler
- can it be one readable line

Make sure to NOT push credentials to GitHub.
