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
| `access_policy.py` | Immutable 14-option website/app catalog; labels/capabilities; strict normalization; site/app projection; `projects.json` loading and task/preset union |
| `logging_setup.py` | Timestamped UTF-8 file and terminal root logging |
| `state.py` | Locked modes, terminal shutdown, grant lifecycle/feedback coordination, versioned monitoring context, retryable policy reconciliation, breaks, allowance, verdicts, and status |
| `storage.py` | Capture JPEGs, LLM exchange JSON, retryable ordered session JSONL, and persisted allowance/topic state |
| `runtime_status.py` | Locked JSON-safe fixed-delay loop cadence, phase, result, countdown, and error state |
| `scheduler.py` | Enforcer (including access expiry and dirty-policy retry), context-safe productivity monitor, and agent-watch loops |
| `blocking/admin.py` | Windows admin test and `runas` self-relaunch |
| `blocking/hosts_blocker.py` | Marker-fenced hosts replacement/removal and DNS-cache flush; dry-run adapter |
| `blocking/app_killer.py` | Case-insensitive exact process-name termination with psutil |
| `monitoring/screen_capture.py` | One Pillow image per physical monitor via mss |
| `monitoring/webcam_capture.py` | Optional DirectShow webcam frame; failure returns `None` |
| `monitoring/stitcher.py` | Labeled vertical monitor/webcam composite |
| `monitoring/analyzer.py` | Original-detail productivity verdict: current alignment on capture 1 and task-aware rolling comparison from capture 2; low-detail single-capture agent-activity verdict |
| `feedback/goal_access.py` | Policy-revision-gated transition acknowledgments and independent FIFO model/TTS worker |
| `feedback/messages.py` | Context-grounded good-luck, nudge, milestone-praise, break, goal-access, and agent-transition text |
| `feedback/tts.py` | OpenAI WAV or pyttsx3 speaker behind one FIFO worker |
| `webui/app.py` | Flask factory and state-changing session, access, break, agent, and disable routes |
| `webui/status.py` | Composition of state and scheduler snapshots |
| `webui/templates/`, `static/` | Actions-first dashboard and safe non-overlapping polling |

## Behavioral invariants

- A new session replaces one-off task access groups, ends any temporary goal-access
  grant, and resets the latest verdict, timeline, break, streak, and agent
  state. Its next monitor tick resets the analyzer window.
- Registered normal shutdown ends and records an active grant before serialized
  hosts cleanup; hard termination can skip both cleanup and the end event.
- OFF and BREAK preserve the in-memory timeline; restart does not. Only
  allowance usage and topic history persist. Live goal-access grants never do.
- A successful productivity capture is evaluated immediately against the
  available rolling window only if its versioned monitoring context still
  matches. Capture one judges only current task alignment and cannot establish
  progress or a stall. From capture two, compare corresponding monitor/webcam
  panels across the whole available oldest-to-newest window.
- `PROGRESS_WINDOW_CAPTURES` is a maximum retained history with a minimum value
  of two, not a comparison threshold. With five captures and the default
  five-minute fixed delay, the maximum window begins on the fifth uninterrupted
  same-context tick and spans at least about 20 minutes; capture and model
  latency extend that timing.
- Task-aware comparison expects meaningful relevant changes from
  artifact-producing coding, writing, editing, note-taking, debugging, and
  active research. Meaningfully unchanged captures with no other task-aligned
  evidence may be stalled from capture two. Plausibly static reading, thinking,
  calls, physical work, and visibly running builds, tests, or training remain
  productive only with concrete topic-aligned engagement evidence. Unrelated
  changes, timestamps, clocks, cursors, animations, webcam lighting, and minor
  posture changes do not establish progress. Do not invent a static-work
  exception for a vague task.
- The analyzer prompt requires every productive reason to integrate a brief
  affirmation tied to concrete task-aligned evidence and asks the model to vary
  the wording naturally. A single capture may praise current engagement but
  must not claim change over time. From capture two, progress praise requires
  supporting task-relevant chronological evidence; otherwise praise only the
  engagement or focus. The canonical reason is stored, displayed, and spoken
  unchanged on ordinary productive ticks. Off-track and 30-minute
  streak-milestone ticks instead generate a nudge or richer praise, while every
  evaluation still queues exactly one utterance.
- Scheduler intervals are fixed delays after a tick finishes, not wall-clock
  schedules. Starting a session does not reset their countdowns.
- Productivity and agent-watch ticks share one capture lock. Hold it only
  around the injected capture callable; persistence, model calls, state
  mutation, and speech must remain outside it.
- The productivity analyzer gets an immutable, revisioned context snapshot.
  Every grant start/end changes that identity and resets the rolling window
  before the next capture. Recheck after capture and atomically compare again
  when recording: a transition during capture/model work must produce
  `context_changed` with no verdict state, event, or speech.
- The canonical access catalog has 14 ordered groups: `reddit`, `youtube`,
  `twitter`, `discord`, `hackernews`, `linkedin`, `bluesky`, `substack`,
  `facebook`, `lesswrong`, `eaforum`, `4chan`, `telegram`, and `steam`.
  Discord grants both its configured websites and desktop app from one choice;
  Telegram and Steam are app-only; every other group is website-only.
- Start, goal-access, and break forms share one repeated `allowed_groups`
  checkbox contract. Strictly normalize and allowlist all values before state,
  events, prompts, speech, hosts, or process mutation. Reject unknown keys and
  either legacy `allowed_sites`/`allowed_apps` field with HTTP 400. The break
  route still trusts HTML duration/type constraints; forged negative social
  minutes can corrupt allowance accounting.
- Task and preset groups remain active during ON and BREAK, are part of the
  analyzer's permanent task context while monitoring is active, spend no social
  allowance, and spare any selected app-capable processes.
- One temporary goal-access grant may be active at a time, but a session may
  contain unlimited sequential grants. Each requires a non-empty goal, at
  least one strictly validated access group, and either 1..240 wall-clock
  minutes or session-end duration. It stays in ON mode, spends no social
  allowance, does not itself pause monitoring, and can spare selected apps.
- BREAK preserves but suspends the entire goal grant: grant-only websites
  re-block and grant-only apps become kill targets while its timer keeps
  running. It resumes only if still active when BREAK ends. Task groups remain
  active and break groups apply only during that BREAK; overlapping scopes are
  additive. Agentic policy can independently permit an overlapping website.
  Timed expiry is detected by the fixed-delay enforcer and may occur during
  BREAK.
- Serialize every desired hosts policy through the state-owned reconciliation
  lock. A backend exception leaves the policy dirty, exposes
  `/status.enforcement.reconciliation_pending`, and is retried by the enforcer;
  never let an older writer overwrite a newer transition. App-only scope
  changes advance monitoring identity and process policy without dirtying or
  rewriting an identical hosts policy.
- Complete goal-access events and successful enforcement precede optional
  transition message/TTS work. Start, manual stop, and expiry each enqueue one
  immutable acknowledgment context. Successful serialized reconciliation moves
  only requests supported by that exact policy revision toward the ready FIFO;
  a superseded failed permission transition is dropped rather than announced.
  A separate daemon worker delivers approved requests without holding the
  lifecycle lock. Cancel an unapplied start if its
  grant ends, expires, is replaced, is disabled, or shuts down before opening
  reconciliation succeeds. Model/speech failure never rolls state back or
  retries a claimed request. Hard termination can lose in-memory speech, but
  canonical lifecycle events are attempted and retained before reconciliation.
- Session-event appends are serialized. A transient JSONL failure retains the
  complete timestamped line for enforcer retry, never prevents immediate hosts
  reconciliation, and rolls partial/close-time writes back to the previous line
  boundary before retry. Matching transition speech waits until earlier events
  are durable. All session, break, agent, and goal transition speech shares the
  FIFO worker so lifecycle acknowledgments cannot overtake each other.
- Positive social-break minutes are reserved in full when the break starts.
  Manual stop charges each started minute and refunds the unelapsed reservation
  to the break's starting local date; natural expiry consumes the full amount.
- Agent-busy mode empties only the website blocklist; it adds no app
  permissions. App killing continues for processes not spared by an active
  task/goal group, and the productivity monitor pauses until a later watcher
  verdict marks the agent idle.
- Each enforcer tick holds the goal-access lifecycle lock while expiring scopes,
  taking the effective process-target snapshot, and running the kill sweep.
  Expired apps become targets on that tick, and a concurrent route cannot grant
  an app between target selection and termination.
- Shared scheduler/Flask state must stay behind the existing locks.
- `/status` must remain JSON-safe, additive, and `Cache-Control: no-store`.
  Canonical group keys/labels coexist with derived site/app arrays in
  `work_access`, `goal_access`, and `break`; equivalent event payloads retain
  derived arrays for diagnostics and older-log readability. Render model text
  as text, never trusted HTML.
- The Flask server stays on `127.0.0.1`. It has no authentication or CSRF
  defense and must not be exposed as a production network service.

## LLM, logging, storage, and privacy invariants

- Log every complete textual prompt and semantic model output to both terminal
  and the timestamped run log; never slice or abbreviate them.
- Permanent task groups, temporary access goals, and temporary website/app
  groups are complete prompt/event data; log and persist them without
  truncation and document that model evaluation uploads them with the capture
  context. Allowed Discord, Telegram, or other group activity remains
  conditionally productive only when concrete visible evidence serves the
  topic and, for a goal grant, its explicit goal.
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
- Keep access-group order, labels, capability projection, strict normalization,
  and project-preset union centralized in `access_policy.py`. All three forms
  must continue to render the shared picker and submit repeated
  `allowed_groups` values.
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
   run `uv run python main.py --smoke`; it covers only the single-capture
   productivity branch. For rolling-comparison changes, also exercise at least
   two same-context captures and inspect the second request. For UI/state
   changes, also exercise the relevant Flask flow or full local app.
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
- Access is intentionally group-based rather than split by backend. An existing
  `projects.json` preset containing `discord` now opens Discord websites and
  spares `discord.exe`; Telegram and Steam are valid app-only preset keys. Do
  not reintroduce separate site/app controls or silently reinterpret that key.
- `/break` strictly validates `allowed_groups` and rejects legacy split access
  fields, but duration and kind still rely on the dashboard's HTML constraints.
  A forged negative social duration can still corrupt allowance accounting.
- Browser-level DoH behavior is not uniform. Windows honors its hosts file in
  the system resolver, while software with its own resolver can bypass that
  path; keep README wording conditional.
- Hard termination can skip `atexit`; manual fenced-section cleanup remains
  necessary.
- Hosts policy is explicit, not wildcard-based. Substack author subdomains and
  other unlisted alternate domains are not covered.
- Productivity vision uses original detail, which preserves supplied image
  dimensions with the default GPT-5.6 Luna model but can increase input tokens
  and latency. `VISION_MODEL` overrides must support original detail; OpenAI
  currently documents it for GPT-5.4 and future models. Wide composites,
  occlusion, ambiguity, and visually static work can still mislead it.
  Agent-watch vision remains low-detail and can miss small screen text. Never
  present either model verdict as ground truth.
