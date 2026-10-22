# Independent fact-check and correction pass

22 October 2026 | Deep Work | Author: Libor Burian

## Abstract and scope

This pass checked maintained repository claims against executable behavior,
focused reproductions, original local artifacts, and primary documentation.
The starting revision was `dbe6684` on `master`; corrections use
`feat/independent-fact-check`. Previous audit conclusions were not used as
evidence. The original 251-test baseline passed, but new cases exposed duration,
returned-response, and dashboard defects. These are corrected without changing
routes, status keys, verdict schemas, allowance rules, or model settings.

This is a software correctness and evidence review, not a model benchmark.
No training, controlled accuracy comparison, causal treatment, or statistical
population estimate was performed. Test counts establish exercised contracts;
successful API calls do not establish truthful model judgments. Confidence
intervals, seed power analyses, and significance claims would be inappropriate
for this small, uncontrolled compatibility check.

## Method and acceptance criteria

Inventory tracked documentation, configuration, Python, JavaScript, templates,
styles, tests, launcher, and reports. Trace repository claims to the narrow
implementation and tests; check external behavior against installed packages
and primary sources. Reproduce suspected bugs before fixes. Keep historical
artifacts unchanged, recording unsupported historical claims as such rather
than reconstructing missing evidence. Compare generated text with the prompt
and capture evidence, without treating a model's answer as an independent fact.

The approved criteria were: the first session end survives repeated OFF
transitions; returned unusable model responses remain inspectable without
becoming verdicts or speech; dashboard text follows mode and policy; prompts
avoid unsupported completion and uninterrupted-focus claims; documentation
states the actual timing and durability boundaries. Counterexamples to those
criteria were failing regression tests or contradictory runtime evidence.

The environment used Python 3.13.14, uv 0.13.0, Node 24.13.0, OpenAI Python
2.44.0, Pydantic 2.13.4, MSS 10.2.0, Pillow 12.3.0, OpenCV 5.0.0.93,
pyttsx3 2.99, Flask 3.1.3, Werkzeug 3.1.8, and pytest 9.1.1. Dependencies were
not upgraded. The live local configuration selected GPT-6 Luna with `xhigh`
reasoning; repository defaults remain `medium`. Image detail remains
`original` for productivity and `low` for agent watching.

## Evidence table: maintained documentation

Every row is dated 22 October 2026. “Corrected” describes the resulting text
or behavior; linked source/tests are the evidence, not a prior audit. A source
link supports its adjacent claim, not every claim in the linked document.

| Surface | Claim, finding, and correction | Supporting evidence | Verification limit |
|---|---|---|---|
| [README](../README.md) | Method, setup, defaults, flow, image, and privacy summaries checked; qualify monitor enumeration, policy counts, fixed delays, returned responses, and speech uploads. Replace remote screenshots with a labeled synthetic fixture. | [main](../main.py), [config](../deepwork/config.py), [lock](../uv.lock), [scheduler](../deepwork/scheduler.py), owning guides below. | Current clone/runtime contract; the screenshot proves display only. |
| [AGENTS](../AGENTS.md) | Invariants checked; freeze completed-session time, distinguish returned refusals from accepted outputs, and narrow speech suppression to before enqueue. Correct readiness and pyttsx3 guarantees. | [state tests](../tests/test_state.py), [response tests](../tests/test_llm_output.py), [server tests](../tests/test_webui_server.py), [speech adapter](../deepwork/feedback/tts.py). | Instructions are maintenance rules, not proof all races or platforms are covered. |
| [CLAUDE](../CLAUDE.md) | Keeps one instruction source through `@AGENTS.md`; no duplicated behavioral contract. | [Claude memory documentation](https://code.claude.com/docs/en/memory#agentsmd). | Import syntax checked; no Claude session executed. |
| [Documentation index](../docs/README.md) | Ownership/navigation checked; add this evidence record without copying detailed contracts. | Linked files and headings. | Navigation is not behavioral validation. |
| [User guide](../docs/user-guide.md) | OFF/BREAK/busy descriptions, zero allowance, task/goal exceptions, elapsed-session accounting, sampled milestones, and watcher interpretation corrected. | [state](../deepwork/state.py), [Flask tests](../tests/test_webui.py), [dashboard tests](../tests/dashboard.test.cjs). | Browser fixture uses injected collaborators. |
| [Architecture](../docs/architecture.md) | Diagram and module map include shared response handling; fixed-delay, capture-lock, readiness, ordered-event, and speech boundaries checked. Explicitly retain watcher race and delayed approved-message limitations. | [scheduler tests](../tests/test_scheduler.py), [runtime tests](../tests/test_runtime_status.py), [feedback](../deepwork/feedback/goal_access.py). | A characterization test demonstrates one stale watcher outcome; it does not repair it. |
| [Privacy and data](../docs/privacy-and-data.md) | Returned refusals/incomplete responses are recorded before validation; direct writes may fail. Upload and retention wording distinguishes images, text, speech, and local files. | [storage](../deepwork/storage.py), [response handler](../deepwork/llm_output.py), [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data). | Account controls and provider policy may change; local files are unencrypted. |
| [Startup](../docs/startup.md) | Readiness means received HTTP status and headers, including non-2xx; response body/content is not validated. | [server](../deepwork/webui/server.py), [HTTPConnection](https://docs.python.org/3.13/library/http.client.html#http.client.HTTPConnection), [server tests](../tests/test_webui_server.py). | No new live UAC or browser-launch run; startup executable behavior unchanged. |
| [Troubleshooting](../docs/troubleshooting.md) | Distinguish exceptions before SDK return from recorded unusable replies. “Speech queued” is not playback evidence. Preserve manual hosts recovery caveats. | [response tests](../tests/test_llm_output.py), [TTS](../deepwork/feedback/tts.py), [hosts](../deepwork/blocking/hosts_blocker.py). | No induced real disk, DNS, device, or playback failure. |
| [Verdict corrections](../docs/verdict-corrections.md) | Suppress original feedback only before the speech enqueue check; queued/playing audio is not canceled. Polling waits after request completion. | [scheduler](../deepwork/scheduler.py), [correction route tests](../tests/test_webui.py), [dashboard](../deepwork/webui/static/dashboard.js). | API/schema/accounting unchanged; no claim of retrospective audio cancellation. |
| [Verification](../docs/verification.md) | Add dependency-free Node tests and their test-only prerequisite; remove continuous-cadence, guaranteed monitoring, and ambiguous speech-suppression claims. | [Node runner](https://nodejs.org/api/test.html), all [tests](../tests), commands below. | Stubbed DOM checks do not establish layout or actual enforcement. |
| [Migration report and PDF](2026-10-13-gpt-6-luna.md) | Reconcile measurements with original responses, captures, and logs; qualify missing red-run/lock transcripts, shell execution details, and speech causal explanation. | Five saved responses, two run logs, three test logs, two inspected rolling captures listed in that report; migration Git diff. | Raw evidence stays private; no historical ground-truth accuracy label set exists. |
| [Report index](README.md), this report, and PDFs | Separate compatibility results from correctness checks; provide reproducible renderer and Libor Burian attribution. | [renderer](../scripts/render_report.py), original artifacts, current test/live records below. | Reports compress evidence; they do not replace the original artifacts. |

## Evidence table: source, UI, and configuration

The following groups cover the maintained implementation surface; empty or
documentation-only package `__init__.py` files carry no additional runtime
guarantees. Tests are executable evidence for their specified cases, not proof
of universal correctness.

| Surface | Claim, finding, and correction | Supporting evidence | Verification limit |
|---|---|---|---|
| [state](../deepwork/state.py) | Repeated Disable/shutdown overwrote session end; retain its first value and do not fabricate an end before a session. Frozen dataclasses do not replace locking; tuple defaults need no mutable factory. | New duration regressions in [state tests](../tests/test_state.py); [Python dataclasses](https://docs.python.org/3.13/library/dataclasses.html). | Wall-clock changes and hard termination remain outside this fix. |
| [response handler](../deepwork/llm_output.py), [analyzers](../deepwork/monitoring/analyzer.py), [messages](../deepwork/feedback/messages.py) | Record full returned objects, including refusals/incomplete statuses, before checking usable output; reject missing verdicts and blank messages. | [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [response tests](../tests/test_llm_output.py), [analyzer tests](../tests/test_analyzer.py), [feedback tests](../tests/test_feedback.py). | An SDK exception before return supplies no object to save; direct exchange writes can fail. |
| Prompts in analyzers/messages | Idle means no active work observed; it does not prove successful completion. Milestones are credited sampled minutes. Keep task and active-goal exceptions. Bounded session summary is not complete history. | Same source/tests; live watcher and two synthetic text fixtures below. | Model adherence and inferred attention are not guaranteed. |
| [scheduler](../deepwork/scheduler.py), [runtime status](../deepwork/runtime_status.py) | Intervals are waits after ticks, including skipped ticks. Kill results are requests, not proven exits. Preserve post-capture productivity identity check but document missing watcher recheck. | [scheduler tests](../tests/test_scheduler.py), including stale watcher reproduction; [runtime tests](../tests/test_runtime_status.py). | One captured frame cannot establish continuous work; countdowns are estimates. |
| [Flask app](../deepwork/webui/app.py), [status composition](../deepwork/webui/status.py) | Render checkbox from the locked state snapshot; maintain JSON-safe status, exact correction validation, escaped text, and additive policy fields. | [web tests](../tests/test_webui.py), [picker tests](../tests/test_unified_picker_ui.py). | Loopback still has no authentication or CSRF defense. |
| [template](../deepwork/webui/templates/index.html), [JS](../deepwork/webui/static/dashboard.js), [CSS](../deepwork/webui/static/dashboard.css) | Fix mode descriptions, zero-cap display, checkbox synchronization, desired-policy label, and process-request wording. Preserve unsaved local checkbox changes during polling. | 12 [Node checks](../tests/dashboard.test.cjs), Flask rendering checks, browser form exercise and screenshot. | Synthetic runtime telemetry; no new mobile-layout claim. |
| [main](../main.py), [server](../deepwork/webui/server.py), [launcher](../Start%20Deep%20Work.bat), [admin](../deepwork/blocking/admin.py) | Cleanup is best-effort; startup binds before browser worker. Repair administrator API source link and readiness description. | [main](../tests/test_main.py), [server](../tests/test_webui_server.py), [launcher tests](../tests/test_launcher.py); [IsUserAnAdmin](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-isuseranadmin). | Live UAC, hosts changes, and launcher not re-exercised in this pass. |
| [hosts blocker](../deepwork/blocking/hosts_blocker.py), [app killer](../deepwork/blocking/app_killer.py) | Explicit names only; browser resolver behavior varies. A successful `kill()` return is a termination request; no wait proves exit. Empty results do not prove no matching process existed. | [hosts tests](../tests/test_hosts_blocker.py), [process tests](../tests/test_app_killer.py), [psutil](https://psutil.readthedocs.io/en/latest/#psutil.Process.kill), [TerminateProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-terminateprocess). | Real hosts rewrite/flush and process termination not exercised. |
| [access policy](../deepwork/access_policy.py), [config](../deepwork/config.py), [.env example](../.env.example) | Fourteen groups and union semantics match tests. Remove unused `SOCIAL_SITES`; allowance depends on exact break kind. One-dot `www` expansion is a heuristic, not domain classification. dotenv is called at startup. | [access tests](../tests/test_access_policy.py), [config tests](../tests/test_config.py), [dotenv](https://bbc2.github.io/python-dotenv/), [Public Suffix List explanation](https://publicsuffix.org/learn/). | Explicit domain catalog is incomplete by design; numeric validation remains limited. |
| [screen capture](../deepwork/monitoring/screen_capture.py), [webcam](../deepwork/monitoring/webcam_capture.py), [stitcher](../deepwork/monitoring/stitcher.py) | Fresh MSS instance is a design choice, not required for all threaded use. Webcam release closes this handle, not a guarantee about LEDs/other consumers. JPEG quality 80 does not “halve” default; default font is not guaranteed bitmap. | [capture tests](../tests/test_capture_stitch.py), [MSS usage](https://python-mss.readthedocs.io/stable/usage.html), [OpenCV VideoCapture](https://docs.opencv.org/4.x/d8/dfe/classcv_1_1VideoCapture.html), [Pillow JPEG](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#jpeg), [fonts](https://pillow.readthedocs.io/en/stable/reference/ImageFont.html#PIL.ImageFont.load_default). | Installed OpenCV 5 binding tested live; linked 4.x page documents the shared capture API, not a 5.0-specific behavior guarantee. |
| [TTS](../deepwork/feedback/tts.py), [transition worker](../deepwork/feedback/goal_access.py) | Log “queued,” not “speaking.” `pyttsx3.init()` can reuse an engine; invoking it per utterance is not proof of a fresh engine or upstream bug cure. Ready transitions may speak after later policy changes. | [pyttsx3 factory](https://pyttsx3.readthedocs.io/en/latest/engine.html#the-engine-factory), [feedback tests](../tests/test_feedback.py), live backend-return instrumentation. | Queue drain does not itself establish successful or audible playback. |
| [logging](../deepwork/logging_setup.py), [storage](../deepwork/storage.py) | Log complete returned output; timestamps reduce but do not guarantee filename collisions never occur. Windows streams are not universally CP1252. Preserve direct-write and ordered-JSONL limits. | [logging tests](../tests/test_logging_setup.py), [storage tests](../tests/test_storage.py), [Python standard streams](https://docs.python.org/3.13/library/sys.html#sys.stdin). | No encryption, automatic pruning, atomic replacement, or cross-process locking added. |
| [project metadata](../pyproject.toml), [lock](../uv.lock), [.python-version](../.python-version), [.gitignore](../.gitignore), [.gitattributes](../.gitattributes) | Declared versions/defaults checked; lock unchanged. Credentials/runtime paths ignored; PDF binary treatment retained. Remove unsupported “must use CRLF” wording. | `uv lock --check`, installed versions, Git ignore/diff checks; [Git attributes](https://git-scm.com/docs/gitattributes). | Not an upgrade or cross-platform dependency certification. |
| [tests](../tests) and [PDF renderer](../scripts/render_report.py) | Remove unverifiable historical test-order comments; add regression evidence. Renderer uses isolated pinned document dependencies, escapes inline text, and rejects unsupported Markdown. | Python/Node runs, PDF text/metadata/layout inspection; [ReportLab flow](https://docs.reportlab.com/reportlab/userguide/ch5_platypus/), [Mistune AST](https://mistune.lepture.com/en/latest/upgrade.html#astrenderer). | Renderer supports this report subset, not arbitrary Markdown or mathematical typesetting. |

SDK retries were also rechecked: OpenAI Python documents retries for certain
connection/status errors, not a guarantee to regenerate a semantically invalid
answer. See its [retry contract](https://github.com/openai/openai-python/tree/v2.44.0#retries).
Browser DNS was checked against [Chromium's resolver design](https://chromium.googlesource.com/chromium/src/+/main/net/dns/README.md):
DoH does not uniformly imply bypassing hosts entries. No universal browser
blocking claim is made.

## Verification results and learnings

Duration, refusal/empty-output, incomplete-status, and checkbox tests were
observed failing before their fixes. The initial JavaScript cases exposed
10 failures out of 12. After corrections the Python suite passed 277 tests
and the Node suite passed all 12. `uv lock --check`, CLI help, and diff checks
passed. These tests cover deterministic contracts with injected collaborators;
they do not count as device, network, or enforcement end-to-end tests.

The isolated Flask browser fixture exercised ON/busy, retained busy state
during BREAK, and OFF through actual break/Disable forms. The browser displayed
zero allowance correctly, initialized the enabled watcher checkbox, and kept
an unsaved uncheck across later polls. Pending desired policy was visible.
ON/idle and process-result edge cases were additionally checked by Node tests.
Browser inspection exposed a remaining absolute “agent is working” label;
it now says the watcher reports activity. The public screenshot contains only
synthetic state. Its injected scheduler status is not a real scheduler run.

The real smoke command exited 0. Then two directly invoked monitor ticks in
one unchanged context accepted usable responses; the second request carried
both chronological captures and the `COMPARISON (2/5)` header. All three new
composites were 960 by 1896 pixels and contained two monitor panels plus webcam.
Inspection confirmed broad visible app changes described by the rolling
response, not every inferred action or productivity judgment. The two direct
ticks were about 27 seconds apart, not the normal five-minute fixed delay.
Configured credited intervals therefore are not measured elapsed work.

Smoke and rolling work produced nine completed Responses exchanges: three
productivity, three nudge, one watcher, and two additional text checks. The
last two used explicitly synthetic contexts for idle/input-needed wording and
sampled-minute praise; their output was not spoken. Their responses avoided
claiming guaranteed completion or uninterrupted attention. The watcher again
reported idle despite a visible active agent status: this is an observed
model limitation, not a corrected accuracy result. The selected model/detail
settings were preserved as scoped.

The two rolling speech requests returned HTTP 200, the instrumented backend
calls returned normally, and both queue-drain assertions passed. This is
stronger evidence than queue drain alone, because the worker catches speech
exceptions. Audible quality was not measured. Neither new run log contained
an ERROR record. This does not establish absence of silent errors or guarantee
future API/device success. No real hosts writes, app killing, long-period
scheduler cadence, or UAC were exercised in these live checks.

## Historical reconciliation and evidence retention

Before these new runs, 1,699 local response JSON files and 1,198 session JSONL
records were parsed successfully. This inventory checked readability and
response/event structure; it did not validate every observation. The response
inventory contained 917 productivity, 688 message, and 94 watcher files.
Only the migration report's cited captures and the current live captures were
visually reconciled in detail. The original migration logs establish its green
test counts and request timings, but do not preserve every shell exit status
or its stated initial red run. Corrections to that report are explicitly dated;
raw captures, responses, and logs remain unchanged and untracked.

Current local evidence: `logs/deepwork_20261022_221200.log` and
`logs/deepwork_20261022_221508.log`; captures `20261022_221206_079057`,
`20261022_221514_107328`, and `20261022_221541_471457` under `results/captures/`;
response timestamps `221220_574157`, `221222_963251`, `221523_454631`,
`221524_974381`, `221554_457370`, `221557_639672`, `221632_544659`,
`221635_755052`, and `221636_971665` with date prefix `20261022_` under
`results/llm/`. Sensitive pixels and response contents are deliberately not
included in this public report. Private verification helpers and link-check
results remain under ignored `results/fact-check-20261022/`.

An initial 118-URL scan found broken upstream paths and access-restricted or
timed-out requests. Broken administrator, Windows DNS, OpenCV, and MSS paths
were repaired; the speech-format reference uses Microsoft RIFF documentation.
A 403 from an API-key/help page is a verification limit, not evidence that the
page is nonexistent. The old remote README images were replaced with the
current local fixture image. Reachability alone does not establish that a
source supports a claim; the relevant primary documentation was read as well.

## Discussion and remaining limits

The principal lesson is to distinguish an intended policy, an attempted
operation, a returned model object, and an observed outcome. Tests that only
provide successful parsed replies missed refusal evidence loss. Repeated OFF
transitions needed an invariant about the first end time. The dashboard needed
mode-aware text and a separate unsaved form value. Shared response handling and
existing state locks solve these narrow defects with less duplication than
per-workload patches or a new state architecture.

One bounded review checked correctness, security/privacy, reliability,
maintainability, architecture, and unsupported claims. Known limits remain:
watcher results can be stale after concurrent transitions; already approved
feedback can describe an older transition; queued audio is not canceled;
cleanup and direct file writes are not durable guarantees; hosts enforcement
is explicit-name and bypassable; and model observations can be wrong. This
pass does not certify that every historical model judgment is factual or that
all possible defects have been removed.

Reproduction commands and side effects are owned by the
[verification guide](../docs/verification.md). PDF generation is owned by the
[report index](README.md#rebuild-the-papers). Future measurements should specify
their target outcome and independent labels before making accuracy or causal
claims; this pass makes neither.
