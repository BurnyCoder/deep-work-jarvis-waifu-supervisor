# AGENTS.md — orientation for AI agents (and humans) working on this repo

## What this is

A Windows 11 productivity enforcement app: hosts-file website blocking,
distraction-app killing, five-minute rolling AI screen/webcam progress
monitoring with OpenAI vision, five-minute spoken LLM feedback, ON/OFF/BREAK
modes with a daily social-media allowance, a confirmation-phrase gate, a local
Flask control panel, and results storage. Python 3.13, uv-managed local `.venv`.

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
| `state.py` | thread-safe `SessionState`: modes, breaks, allowance, current-session verdict history, enforcement/status snapshots, phrase gate |
| `storage.py` | `results/` writers: capture JPEGs, uncut LLM JSON, session JSONL, `state.json` |
| `scheduler.py` | enforcer/monitor/agent-watch threads; capture→rolling analysis→one utterance; publishes loop results to runtime telemetry |
| `runtime_status.py` | locked, JSON-safe scheduler cadence/phase/last-next-run/result/error telemetry |
| `blocking/admin.py` | `IsUserAnAdmin` check + `ShellExecuteW("runas")` self-relaunch |
| `blocking/hosts_blocker.py` | marker-fenced idempotent hosts edits + `ipconfig /flushdns`; `DryRunBlocker` for dev |
| `blocking/app_killer.py` | psutil sweep killing target process names |
| `monitoring/screen_capture.py` | mss per-monitor grabs → PIL |
| `monitoring/webcam_capture.py` | OpenCV `CAP_DSHOW` single frame, non-fatal on failure |
| `monitoring/stitcher.py` | labeled vertical composite of all captures |
| `monitoring/analyzer.py` | newest 1–N captures in a bounded rolling progress window → `responses.parse` → `ProductivityVerdict`; `AgentActivityChecker` single-capture "is the AI agent busy?" poll for agentic mode |
| `feedback/messages.py` | LLM-written good-luck / nudge / praise / break-ack sentences |
| `feedback/tts.py` | OpenAI TTS→WAV→winsound or pyttsx3; single `SpeechQueue` worker |
| `webui/app.py` + `status.py` | Flask routes and additive no-cache `/status` payload composition |
| `webui/templates/` + `static/` | status-first responsive dashboard; safe three-second polling and current-session evaluation timeline |

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

# Rules to follow

Make the simplest possible actually practically functioning implementations of new features as a starter, not just demos.

When figuring out a solution, search the web on how others do it and how to do it, including docs.

The code should be modular and functions/classes abstract with implementation details hidden as you go deeper, split it into files, there should be one abstracted wrapper file that calls different clearly named readable phases as imported modular functions.

Split it into modular files and directories as complexity grows.

Do not duplicate code, use reusable functions for various features, and call them, when possible.

Add comprehensible timestamped logging, make sure all prompts and outputs are written to timestamped logs file and terminal realtime.

Make sure all prompts and outputs from LLMs are written into logs without being cut off.

Add comments to each file, function and line of code with local explanation and global context sections. Actually explain how the line does it. Don't generate them using scripts, edit each line using file edit tool. Search the web for context.

Make sure as many lines of code as possible are grounded in some library docs, guides on the internet, github repos, programming language docs, etc., and source link them in comments. Make sure to double-check the accuracy of your code while implementing code from these sources to minimize hallucinations.

Use .env for config.

Use uv.

Use uv unit.

Use local venv in this folder.

Use the current working directory.

Make sure all important details are in README.md.

Make sure README.md and AGENTS.md is updated according to the codebase.

Make sure that how to install, setup and use everything is included in README.md.

Make sure that the github repo includes all information to make it replicable for anyone cloning the repo.

Add documentation.

Add a graph-based visualization of the architecture to README.md .

Create github repo on my account in terminal.

Split commits into meaningful functional units.

Create new branches, pull requests, and merges, for features, on your own, instead of the user. Merge PRs on your own, always.

Do test driven development.

When testing, run the whole pipeline like a user would. Make sure to inspect logs and fix issues if you find any in the logs or overall. Keep running and fixing until it all works flawlessly in logs and the output makes sense. Outputs from LLMs should correspond to README descriptions, and to prompts in code. After each fix, push it to github, run, repeat, look for fixes, fix, repeat, continue until it all works flawlessly in logs and the output makes sense.

Do code review with correctness, security, maintainability, tests, reliability, design and architecture review. Double-check for hallucinations. Do not loop in code review for too long, just do one pass.

Before writing anything, ask yourself:
- does it need to exist
- does standard library or some library or github repo already do it
- can it be simpler
- can it be one readable line

Make sure to NOT push credentials to GitHub.

Make sure important files are pushed.
