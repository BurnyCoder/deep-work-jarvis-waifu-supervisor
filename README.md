# Deep Work: Windows Productivity Enforcement App

Holds you to deep focus on Windows 11: blocks distracting websites, kills
distraction apps, compares a rolling history of your screens + webcam for
visible progress, and speaks a fresh encouragement or gentle nudge every five
minutes, all controlled from a readable realtime local dashboard.

## Features

1. **Website blocking**: Reddit, YouTube, Twitter/X, Discord, Hacker News,
   LinkedIn, Bluesky, Substack, Facebook, LessWrong, EA Forum and 4chan (plus
   known variants like `old.reddit.com`, `youtu.be`, `x.com`) are redirected
   to `127.0.0.1` via the Windows hosts file, IPv4 and IPv6, inside a fenced
   `# >>> deepwork block` section that is cleanly removed on OFF/exit.
2. **App killing**: a background sweep terminates Discord, Telegram and
   Steam every 3 seconds while enforcement is on.
3. **Rolling progress monitoring**: every 5 minutes all monitors and the
   webcam are captured and stitched into one labeled image. Every capture
   triggers an OpenAI vision evaluation over the newest 1–5 captures, ordered
   oldest to newest; after warm-up, this is always the latest 25-minute
   window. The coach compares documents, code, tests, research and other
   visible task state for real progress. A full on-topic window with no
   meaningful progress gets a gentle stalled-work nudge, while plausible
   reading/thinking work is not rejected merely for looking static. Websites
   explicitly required for the task are judged by whether their visible use
   advances that task, not treated as automatically productive or distracting.
4. **Spoken feedback every 5 minutes**: an immediate LLM-written good-luck
   message starts the session, then every successful monitoring evaluation
   produces exactly one spoken update. Ordinary productive checks speak the
   fresh vision reason directly; distraction or stalled work gets a
   context-rich nudge; every 30 consecutive productive minutes gets praise.
   Voice pauses while OFF, on BREAK, or while an agentic coding agent is busy.
   OpenAI TTS voices are AI-generated, not human. Offline `pyttsx3` remains
   available via `TTS_ENGINE=pyttsx3`.
5. **Modes**: **ON** (everything enforced), **OFF** (nothing), **BREAK**
   (timed, auto-restoring; you state what it's for and how long, TTS
   acknowledges). Breaks can allow only specific sites/apps
   (`reddit,discord`) while everything else stays blocked, and come in two
   kinds: *social media* (draws from a **2 h/day allowance**, refused once
   exhausted) or *away from computer*. When starting focused work, you can
   select any blocked website groups genuinely required for that task; only
   those sites open, normal monitoring continues, and no break minutes are
   charged. Optional `projects.json` presets add reusable site selections.
6. **Confirmation phrase** : turning enforcement off requires typing exactly
   `I will not stop cool deepwork session`.
7. **Realtime web dashboard**: `http://127.0.0.1:5000` by default (port via
   `UI_PORT`) puts live status before the controls. It shows mode, topic,
   session duration, monitoring and evaluation countdowns, streak and social
   allowance, task-required website access, current-session evaluation
   history, break/agent state, active blocking counts, and scheduler health.
   Each evaluation keeps its complete reason visible and its full
   screen/webcam observation in an expandable disclosure.
8. **Agentic engineering mode**: tick *agentic engineering* when starting a
   session (or toggle mid-session). A vision check every 60 s
   (`AGENT_CHECK_INTERVAL_S`) watches your screens for an AI coding agent
   (Claude Code, Cursor, terminal agents) that is actively working — spinner,
   streaming output, running tools. While it works, **everything unblocks**
   so you can scroll Twitter guilt-free; the moment it finishes or waits for
   your input, the session's normal blocklist snaps back while explicitly
   task-required sites remain open, and the voice calls you over to review.
   Waiting time is free (no 2 h allowance drain), and productivity nudges
   pause while the agent runs. Cost: one low-detail capture per minute, a few
   cents per workday.
9. **Results storage**: `results/captures/*.jpg` (stitched images),
   `results/llm/*.json` (full, uncut LLM request/response pairs),
   `results/sessions/*.jsonl` (timestamped event log), `results/state.json`
   (allowance + topic history, survives restarts). Runtime logs stream to the
   terminal and `logs/deepwork_*.log` simultaneously.

## Architecture

`main.py` remains the readable wrapper that wires configuration, state,
storage, enforcement, monitoring, feedback and the local web UI. The rolling
monitoring path is:

```mermaid
flowchart TD
    Main["main.py<br/>config + object wiring"] --> UI["Flask control panel"]
    Main --> Scheduler["Scheduler threads"]
    Main --> State["SessionState"]
    UI -- "task sites + optional preset" --> Access["site_access policy<br/>validate + ordered union"]
    Access --> State
    UI -- "GET /status every 3 s" --> Status["Status payload composer"]
    Status --> State
    Status --> Runtime["RuntimeStatus<br/>loop cadence + health"]
    Scheduler --> Runtime
    State --> Effective["Effective access<br/>full blocklist − allowed task/break sites"]
    Effective --> Enforcer["Enforcer<br/>hosts + app killing"]
    Scheduler --> Enforcer
    Scheduler --> Gate{"Focused monitoring active?"}
    Gate -- "OFF / BREAK / agent busy" --> Quiet["No capture or periodic voice"]
    Gate -- "yes, every 5 min" --> Capture["Capture monitors + webcam<br/>stitch and store JPEG"]
    Capture --> Window["ProductivityAnalyzer<br/>topic + allowed sites + newest 1–5 captures"]
    Window --> Vision["OpenAI Responses API<br/>multi-image structured verdict"]
    Vision --> State
    State --> Outcome{"Nudge or 30-min praise?"}
    Outcome -- "yes" --> Message["Context-rich MessageGenerator"]
    Outcome -- "ordinary productive tick" --> Reason["Fresh verdict reason"]
    Message --> Speech["Single SpeechQueue worker"]
    Reason --> Speech
    Speech --> TTS["OpenAI TTS or pyttsx3"]
```

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

Environment configuration lives in `.env`: see `.env.example` for every variable
(models, reasoning effort, intervals, rolling progress-window size, TTS
engine/voice, allowance cap, UI port). Productivity evaluation defaults to
`VISION_MODEL=gpt-5.6-sol` with `PROGRESS_REASONING_EFFORT=xhigh`;
`PROGRESS_WINDOW_CAPTURES=5` means each evaluation compares up to the five
latest captures. The frequent agent-busy poll remains on
`AGENT_VISION_MODEL=gpt-5.4-mini`. Older `.env` files using `BATCH_SIZE`
still work.

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

Then open **http://127.0.0.1:5000** (or the `UI_PORT` from `.env`), type what
you'll work on, optionally check only the websites required for that task, and
press **Start**. You'll hear your good-luck message immediately, then a fresh
progress-aware voice update after each five-minute monitoring tick.

### Realtime dashboard

The browser fetches `/status` every three seconds and updates countdowns once
per second between requests. Polls never overlap, pause while the tab is
hidden, and resume immediately when you return. If the local server is briefly
unreachable, the dashboard keeps the last good data visible and shows
**Reconnecting** instead of blanking the page.

Productivity history is scoped to the **current session**:

- Every completed evaluation appears newest-first with its timestamp,
  productive/off-track label, full reason, and expandable full observation.
- BREAK and OFF preserve the completed timeline so it can still be reviewed.
- Starting a new session clears the visible timeline and latest verdict.
- Restarting the program clears the in-memory dashboard history; durable
  verdict events remain in `results/sessions/*.jsonl`.

The operations cards report the actual number of blocked domains and watched
process names plus each scheduler loop's cadence, phase, previous result,
next-run countdown, and latest error. `/status` is also a documented,
no-cache JSON endpoint for local inspection:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/status
```

The panel remains bound to `127.0.0.1`; it displays textual AI observations
but does not serve saved capture images or raw prompts.

### Task-scoped website access and saved presets

The Start form lists every blocked website group. Checked groups stay open
until the next focused session starts; an unchecked group remains blocked.
This is productive-work access, so:

- the five-minute screen/webcam evaluation and spoken feedback stay active;
- the daily social-break allowance is not reduced;
- Discord, Telegram, and Steam desktop processes are still killed;
- a timed break temporarily adds its own site/app allowances; and
- after agentic waiting ends, task-required sites remain open while the rest
  re-block.

One-off selections are intentionally not written to `results/state.json`; a
new session defaults to no task access. The current choices and their effective
union are visible on the dashboard and at `/status` under `work_access`.

For reusable selections, create `projects.json` in the repo root, e.g.:

```json
{"ml-research": ["twitter"], "community": ["discord", "bluesky"]}
```

Selecting a preset adds its groups to the one-off checkboxes, with duplicates
removed. Valid group names are the keys of `SITE_DOMAINS` in
`deepwork/config.py` (reddit, youtube, twitter, discord, hackernews,
linkedin, bluesky, substack, facebook, lesswrong, eaforum, 4chan). Invalid JSON,
unknown groups, or an invalid preset shape stop startup with a clear log error
instead of silently weakening enforcement.

## Verifying it works (manual smoke checklist)

1. `uv run python main.py` → accept the UAC prompt.
2. Start a session allowing `twitter` and `linkedin`; check
   `C:\Windows\System32\drivers\etc\hosts` has the
   `# >>> deepwork block start` section, does not contain `x.com` or
   `linkedin.com` inside that section, and still maps `reddit.com` to
   `127.0.0.1`.
3. Launch Discord or Steam: it dies within ~3 s.
4. Take a 1-minute social break allowing `reddit`: TTS acknowledges, Reddit
   unblocks, and a minute later blocking auto-restores (watch the log).
5. `/disable` with a wrong phrase → refused (403). With the exact phrase →
   everything off and the hosts section removed.
6. Run `uv run python main.py --smoke`: one real capture is evaluated and
   spoken exactly once.
7. Keep the dashboard open through two evaluations: task access is shown,
   both evaluations appear newest-first,
   the reason is readable, and **What the monitor saw** expands to the full
   observation. Check the live enforcement and scheduler cards as well.
8. Inspect `logs/`, `results/sessions/`, and `results/llm/`: the session event
   records selected/effective site keys, the vision prompt names the allowed
   sites and conditional task-alignment rule, and every full LLM response is
   present untruncated.

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
- **Model names churn.** `VISION_MODEL`/`AGENT_VISION_MODEL`/`TEXT_MODEL`/
  `TTS_MODEL` are plain `.env` strings: check the
  [OpenAI model guide](https://developers.openai.com/api/docs/guides/latest-model)
  and [pricing page](https://developers.openai.com/api/docs/pricing) when
  models are retired or when tuning quality, latency, and cost.
- **Cost**: after warm-up, one vision request containing five low-detail
  images and one TTS request run every five minutes of focused work. This is
  intentionally more API usage than the old once-per-25-minute batch.
  GPT-5.6 Sol at `xhigh` prioritizes evaluation quality over latency and cost;
  lower `PROGRESS_REASONING_EFFORT` after representative testing if desired.
  [OpenAI documents](https://developers.openai.com/api/docs/guides/images-vision#giving-a-model-images-as-input)
  that every image in a multi-image request counts toward billed tokens.

## Development

See `AGENTS.md` for architecture, module map, conventions (TDD, dependency
injection, source-linked comments) and gotchas. Tests: `uv run pytest`.
