# Deep Work — Windows Productivity Enforcement App

Helps you hold deep focus during work sessions on Windows 11 by combining
website blocking, distraction-app killing, AI-powered screen/webcam
monitoring, and spoken LLM-generated feedback.

> **Status:** under construction — modules land one feature branch at a time.
> This README grows with the codebase.

## Features (planned → implemented as commits land)

1. **Website blocking** — hosts-file redirect of Reddit, YouTube, Twitter/X,
   Discord, Hacker News, LinkedIn, Bluesky, Substack, Facebook, LessWrong,
   EA Forum, 4chan to 127.0.0.1.
2. **App killing** — continuous psutil sweep terminating Discord, Telegram, Steam.
3. **AI monitoring** — every 5 min: screenshot all monitors + webcam photo,
   stitch into one labeled image; every 5 captures, one OpenAI vision call
   returns `{productive: yes/no, reason}`.
4. **Spoken feedback** — OpenAI TTS speaks LLM-written good-luck messages,
   gentle nudges when unproductive, and praise after 30 productive minutes.
5. **Modes** — ON / OFF / BREAK (timed, auto-restoring, with per-break site/app
   allowances), 2 h/day social-media allowance, per-project social allowlists.
6. **Confirmation phrase** — disabling requires typing
   `I will not stop cool deepwork session`.
7. **Local web UI** — Flask control panel at http://127.0.0.1:5000.
8. **Results storage** — captures, uncut LLM logs, and session records in `results/`.

## Setup

Requires: Windows 11, [uv](https://docs.astral.sh/uv/), an OpenAI API key,
and an **Administrator terminal** (hosts-file editing needs elevation).

```powershell
git clone <this-repo>
cd deep-work
uv sync                      # creates .venv with Python 3.13 and installs deps
copy .env.example .env       # then put your real OPENAI_API_KEY in .env
```

## Run

```powershell
uv run pytest                # unit tests (no admin or API key needed)
uv run python main.py        # starts the app (UAC prompt) + web UI
```

## Repository layout

See `AGENTS.md` (written alongside the code) and inline comments — every
non-obvious line links the doc or guide it is based on.
