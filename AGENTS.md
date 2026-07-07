# AGENTS.md — orientation for AI agents (and humans) working on this repo

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
