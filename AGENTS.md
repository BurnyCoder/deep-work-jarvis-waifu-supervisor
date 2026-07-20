# AGENTS.md — repository operating guide

## Product and source of truth

This Windows 11 productivity-enforcement app combines explicit hosts entries,
exact-name process killing, rolling OpenAI screen/webcam evaluation, spoken
feedback, session modes/exceptions, a loopback dashboard, and local storage.

When documentation and implementation disagree, verify behavior in this order:

1. Executable code and focused tests.
2. `.env.example`, `pyproject.toml`, and `uv.lock`.
3. `README.md`, this file, and other prose.
4. Current authoritative upstream documentation for external behavior.

Do not preserve a claim merely because an older README or comment says it.

## Working commands

Run from the repository root with the uv-managed local `.venv`:

```powershell
uv sync --locked                   # reproduce the checked-in lockfile
uv sync                            # update after an intentional dependency edit
uv run pytest                      # complete fake-backed unit suite
uv run python main.py --help       # CLI surface
uv run python main.py --dry-hosts  # UI + scheduler; no UAC/hosts writes
uv run python main.py --smoke      # one real capture/vision/speech tick
uv run python main.py              # UAC + real hosts enforcement + UI
```

Unit tests need no admin, API, capture, or audio; `--smoke` uses the last three.
After Start, `--dry-hosts` still kills apps, captures, calls APIs, stores, and speaks.

`Start Deep Work.bat` self-elevates and runs the app, but its browser helper is
fixed at `5599` while the app defaults to `5000`. Keep both values aligned.

## Wrapper and module ownership

`main.py` must remain the readable wrapper:

```text
arguments → elevation → config/logging → blocker selection
          → collaborator wiring → cleanup registration → run mode
```

Implementation details live under `deepwork/`:

| Module | Current responsibility |
|---|---|
| `config.py` | Frozen `.env`-derived `Config`; hardcoded site/app policy tables |
| `site_access.py` | Site labels; strict task/preset key normalization; `projects.json` loading and union |
| `logging_setup.py` | Timestamped UTF-8 file and terminal root logging |
| `state.py` | Locked modes, task access, breaks, allowance, streak, verdict history, agent state, status snapshots |
| `storage.py` | Capture JPEGs, LLM exchange JSON, session JSONL, and persisted allowance/topic state |
| `runtime_status.py` | Locked JSON-safe fixed-delay loop cadence, phase, result, countdown, and error state |
| `scheduler.py` | Enforcer, productivity-monitor, and agent-watch daemon loops |
| `blocking/admin.py` | Windows admin test and `runas` self-relaunch |
| `blocking/hosts_blocker.py` | Marker-fenced hosts replacement/removal and DNS-cache flush; dry-run adapter |
| `blocking/app_killer.py` | Case-insensitive exact process-name termination with psutil |
| `monitoring/screen_capture.py` | One Pillow image per physical monitor via mss |
| `monitoring/webcam_capture.py` | Optional DirectShow webcam frame; failure returns `None` |
| `monitoring/stitcher.py` | Labeled vertical monitor/webcam composite |
| `monitoring/analyzer.py` | Rolling 1..N structured productivity verdict and single-capture agent-activity verdict |
| `feedback/messages.py` | Context-grounded good-luck, nudge, praise, break, and agent-transition text |
| `feedback/tts.py` | OpenAI WAV or pyttsx3 speaker behind one FIFO worker |
| `webui/app.py` | Flask factory and state-changing routes |
| `webui/status.py` | Composition of state and scheduler snapshots |
| `webui/templates/`, `static/` | Status-first dashboard and safe non-overlapping polling |

## Behavioral invariants

- A new session replaces one-off task sites and resets the latest verdict,
  timeline, break, streak, and agent state. Its next monitor tick resets the
  analyzer window.
- OFF and BREAK preserve the in-memory timeline; restart does not. Only
  allowance usage and topic history persist.
- Every successful productivity capture is evaluated immediately against the
  available rolling window. With five captures at a five-minute sampling
  interval, oldest-to-newest visual span is 20 minutes; the first full window
  completes around the fifth tick.
- Scheduler intervals are fixed delays after a tick finishes, not wall-clock
  schedules. Starting a session does not reset their countdowns.
- Productivity and agent-watch ticks share one capture lock. Hold it only
  around the injected capture callable; persistence, model calls, state
  mutation, and speech must remain outside it.
- Task and preset site keys are strictly validated and fail before state or
  hosts mutation. The break route trusts HTML duration/type constraints and
  does not strictly validate CSV keys; forged negative social minutes corrupt
  allowance accounting, while unknown keys have no policy effect.
- Task-required sites stay monitored, spend no allowance, and never spare apps.
- Positive social-break minutes are reserved in full when the break starts.
  Manual stop charges each started minute and refunds the unelapsed reservation
  to the break's starting local date; natural expiry consumes the full amount.
- Agent-busy mode empties only the website blocklist. App killing continues.
  The productivity monitor pauses until a later watcher verdict marks the
  agent idle.
- Shared scheduler/Flask state must stay behind the existing locks.
- `/status` must remain JSON-safe, additive, and `Cache-Control: no-store`.
  Render model text as text, never trusted HTML.
- The Flask server stays on `127.0.0.1`. It has no authentication or CSRF
  defense and must not be exposed as a production network service.

## LLM, logging, storage, and privacy invariants

- Log every complete textual prompt and semantic model output to both terminal
  and the timestamped run log; never slice or abbreviate them.
- Persist each complete SDK response under `results/llm/`. For vision requests,
  persist full text plus capture-file references instead of duplicating base64
  image bytes.
- Keep capture, exchange, session, and state artifacts under `results/`.
- Screen and optional webcam images are sensitive and are uploaded to OpenAI
  for vision requests. `pyttsx3` makes only speech playback offline.
- `.env`, `logs/`, and `results/` remain gitignored. Never stage credentials or
  runtime captures, even with a force-add.
- Preserve the dashboard's AI-voice disclosure.

## Implementation rules

Before adding anything, ask:

- Does it need to exist?
- Does the standard library or an established dependency already do it?
- Can the design or line be simpler?
- Can one readable reusable function replace duplication?

Then follow these rules:

- Build the simplest practical, functioning implementation, not a throwaway
  demo.
- Keep the wrapper phase-oriented and hide details in clearly named modules.
  Split files/directories only as complexity actually grows.
- Reuse functions and policy tables; do not duplicate parsing, validation,
  prompt, status, or persistence logic.
- Use `.env` for runtime tunables, uv for dependency management and commands,
  and the repository-local `.venv`.
- Use TDD for behavior changes. Add the failing test first, implement the
  smallest fix, then run the full suite.
- Prefer dependency injection for clients, paths, clocks, and hardware/network
  callables. Tests may monkeypatch narrow OS/library boundaries such as psutil
  iteration or DNS flushing; do not claim that globals are never patched.
- Add global-context and local-behavior comments to files, functions, and code
  lines as requested by the project owner. Ground non-obvious external API and
  platform behavior in current primary documentation links. Write comments
  deliberately with the code; do not mass-generate them.
- Search current library, language, platform, and upstream repository docs
  before implementing unfamiliar behavior. Prefer official/primary sources and
  verify copied API shapes against the installed versions.
- Keep `README.md`, `AGENTS.md`, `.env.example`, architecture diagrams, setup,
  usage, privacy notes, and caveats synchronized with behavior.

## Verification and review

For every change:

1. Run focused tests during TDD.
2. Run `uv run pytest`.
3. Exercise the affected path as a user would. For capture/LLM/TTS changes,
   run `uv run python main.py --smoke`; for UI/state changes, also exercise the
   relevant Flask flow or full local app.
4. Inspect the newest terminal/file logs and relevant `results/` artifacts.
   Confirm prompts, outputs, stored records, and spoken behavior agree.
5. Fix observed issues, rerun the affected path, and push the corrected
   functional commit.
6. Perform one bounded review pass covering correctness, security, privacy,
   maintainability, tests, reliability, design, architecture, and unsupported
   claims.

Do not call a hardware-free unit run an end-to-end smoke test. Do not claim
"flawless" behavior from tests that cannot observe Windows, devices, the
network, or model nondeterminism.

## GitHub workflow

- The existing remote is `BurnyCoder/jarvis-waifu-supervisor`; do not create a
  duplicate or change visibility without explicit authorization.
- Start changes from `master` on `feat/<name>`.
- Preserve unrelated user work. Stage only intended files.
- Split genuinely independent functional units into meaningful commits; do not
  manufacture commit splits for one inseparable documentation correction.
- Push the feature branch, open a pull request, review it, and merge it to
  `master` with a merge commit (`--no-ff`) once checks pass. Complete those
  steps without delegating routine repository operations back to the user.
- Never commit secrets. Confirm important source, tests, configuration
  examples, and docs are tracked before merging.

## Current gotchas

- During the 2026-07-20 audit, `wslrelay` occupied port `5000` on the
  development machine. `UI_PORT` can move the app, but the batch launcher's
  hardcoded browser URL must be changed separately.
- `.python-version` selects Python 3.13. Do not invent a Python 3.14 wheel
  limitation without checking current package indexes.
- The pyttsx3 adapter constructs an engine per utterance to avoid the linked
  upstream reuse issue in `feedback/tts.py`.
- Browser-level DoH behavior is not uniform. Windows honors its hosts file in
  the system resolver, while software with its own resolver can bypass that
  path; keep README wording conditional.
- Hard termination can skip `atexit`; manual fenced-section cleanup remains
  necessary.
- Hosts policy is explicit, not wildcard-based. Substack author subdomains and
  other unlisted alternate domains are not covered.
- Low-detail stitched vision can miss small screen text. Never present model
  verdicts as ground truth.
