# Deep Work — top-level wrapper. This file is deliberately a table of
# contents: each phase below is one clearly-named function from a module that
# hides its implementation details (project rule: "one abstracted wrapper
# file that calls different clearly named readable phases").
# Run:  uv run python main.py            (full app, asks for UAC elevation)
#       uv run python main.py --smoke    (one capture→analyze→speak cycle, no admin)
#       uv run python main.py --dry-hosts (full app, hosts writes only logged)

import argparse
import atexit
from collections.abc import Sequence
import logging
import sys
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    # argparse stdlib CLI parsing: https://docs.python.org/3/library/argparse.html
    p = argparse.ArgumentParser(description="Deep Work productivity enforcement")
    p.add_argument("--smoke", action="store_true",
                   help="run one capture/analyze/speak cycle and exit (no admin needed)")
    p.add_argument("--dry-hosts", action="store_true",
                   help="run everything but only LOG hosts-file changes (no admin needed)")
    p.add_argument(
        "--open-browser",
        action="store_true",
        help="open the dashboard after its local server answers a readiness request",
    )
    # An explicit sequence keeps parser tests hermetic; None retains sys.argv.
    return p.parse_args(argv)


def build_app_objects(cfg, blocker):
    """Construct and wire every collaborator; returns (scheduler, flask_app, extras)."""
    # Imports live here so `--help` stays instant and import order is explicit.
    from openai import OpenAI                      # https://github.com/openai/openai-python

    from deepwork.feedback.goal_access import GoalAccessFeedbackQueue
    from deepwork.feedback.messages import MessageGenerator
    from deepwork.feedback.tts import SpeechQueue, make_speaker
    from deepwork.monitoring.analyzer import AgentActivityChecker, ProductivityAnalyzer
    from deepwork.scheduler import Scheduler
    from deepwork.access_policy import load_project_allowlists
    from deepwork.state import SessionState
    from deepwork.storage import ResultsStore
    from deepwork.webui.app import create_app

    store = ResultsStore(Path("results"))          # requirement 8: results folder
    state = SessionState(daily_social_cap_min=cfg.daily_social_cap_min,
                         project_allowlists=load_project_allowlists(
                             Path("projects.json")
                         ))
    state.load_dict(store.load_state())            # allowance/topics survive restarts

    client = OpenAI(api_key=cfg.openai_api_key)    # one shared API client
    analyzer = ProductivityAnalyzer(
        client=client,
        model=cfg.vision_model,
        store=store,
        window_size=cfg.progress_window_captures,
        reasoning_effort=cfg.progress_reasoning_effort,
    )
    messages = MessageGenerator(
        client=client,
        model=cfg.text_model,
        store=store,
        reasoning_effort=cfg.text_reasoning_effort,
    )
    speech = SpeechQueue(make_speaker(cfg, client))
    goal_access_feedback = GoalAccessFeedbackQueue(state, messages, speech)

    scheduler = Scheduler(state=state, blocker=blocker, store=store,
                          analyzer=analyzer, messages=messages, speech=speech,
                          capture_interval_s=cfg.capture_interval_s,
                          kill_interval_s=cfg.kill_interval_s,
                          # Agentic mode watcher: fast single-capture polls.
                          agent_checker=AgentActivityChecker(
                              client=client,
                              model=cfg.agent_vision_model,
                              store=store,
                              reasoning_effort=cfg.agent_reasoning_effort,
                          ),
                          agent_check_interval_s=cfg.agent_check_interval_s,
                          goal_access_feedback=goal_access_feedback)
    flask_app = create_app(state=state, blocker=blocker, store=store,
                           messages=messages, speech=speech,
                           runtime_snapshot=scheduler.runtime_snapshot,
                           goal_access_feedback=goal_access_feedback)
    return scheduler, flask_app, (state, store, speech)


def run_smoke(scheduler, speech) -> None:
    """Run the real always-evaluate capture→vision→speech path exactly once."""
    scheduler.state.start_session("smoke test")
    scheduler._monitor_tick()                      # the real pipeline, once
    verdict = scheduler.state.last_verdict or {}
    # _monitor_tick queues the only utterance; waiting verifies playback without
    # duplicating the same verdict through a special smoke-only speech path.
    speech.wait_idle(timeout=60)
    log.info("smoke cycle complete: %s", verdict)


def run_mode(
    args,
    cfg,
    scheduler,
    flask_app,
    speech,
    *,
    server_runner=None,
) -> None:
    """Run the selected smoke or long-lived dashboard phase."""

    if args.smoke:
        # Smoke remains a direct single tick and never owns a listening socket.
        run_smoke(scheduler, speech)
        return
    if server_runner is None:
        # Late import keeps `--help` fast and implementation out of the wrapper.
        from deepwork.webui.server import serve_dashboard

        server_runner = serve_dashboard
    scheduler.start()                              # enforcer + monitor threads
    # The server wrapper binds before launching its readiness worker. Direct
    # CLI runs stay manual unless `--open-browser` is explicitly supplied.
    server_runner(
        flask_app,
        cfg.ui_port,
        open_browser=args.open_browser,
    )


def shutdown_runtime(scheduler, state, blocker, store, speech) -> None:
    """Stop producers, serialize final hosts cleanup, and persist local state."""

    from deepwork.feedback.goal_access import InlineGoalAccessFeedback
    from deepwork.state import goal_access_event

    # Stop scheduler producers before publishing OFF. Flask request threads may
    # still be unwinding, so the same state reconciliation lock used at runtime
    # must own the final clear; a direct blocker.clear() could race an older
    # apply and leave its blocklist behind after shutdown.
    try:
        scheduler.stop()
    except Exception:
        log.exception("scheduler shutdown failed")
    goal_feedback = getattr(scheduler, "goal_access_feedback", None)
    if goal_feedback is None:
        goal_feedback = InlineGoalAccessFeedback(
            state,
            scheduler.messages,
            speech,
        )
    with state.goal_access_lifecycle():
        ended_goal_access = None
        shutdown_at = datetime.now()
        try:
            ended_goal_access = state.begin_shutdown(now=shutdown_at)
        except Exception:
            log.exception("shutdown state transition failed")
        try:
            if ended_goal_access is not None:
                state.cancel_pending_goal_access_start(ended_goal_access)
                store.append_session_event(goal_access_event(
                    "goal_access_ended",
                    ended_goal_access,
                    ended_at=shutdown_at,
                    reason="shutdown",
                ))
        except Exception:
            log.exception("shutdown goal-access event persistence failed")
        enforcement_succeeded = False
        try:
            state.reconcile_enforcement(blocker)
            state.mark_goal_access_feedback_policy_applied()
            enforcement_succeeded = True
        except Exception:
            log.exception("final hosts cleanup failed")
        try:
            retry_events = getattr(store, "retry_session_events", None)
            if retry_events is not None:
                retry_events()
        except Exception:
            log.exception("final session-event retry failed")
        if (
            enforcement_succeeded
            and not getattr(store, "session_events_pending", False)
        ):
            state.release_goal_access_feedback()
    # Optional model/TTS work is outside the lifecycle lock. Production wake
    # only queues work, so a slow API cannot race or delay final hosts cleanup.
    goal_feedback.wake()
    try:
        store.save_state(state.to_dict())
    except Exception:
        log.exception("final state persistence failed")
    feedback_idle = False
    try:
        feedback_idle = goal_feedback.wait_idle(timeout=5)
        goal_feedback.stop()
    except Exception:
        log.exception("goal-access feedback shutdown failed")
    try:
        # Do not enqueue SpeechQueue's stop sentinel ahead of a still-running
        # feedback model call; both workers are daemons and may be abandoned on
        # process exit after the bounded wait.
        if feedback_idle:
            speech.stop()
        else:
            log.warning("goal-access feedback still busy during shutdown")
    except Exception:
        log.exception("speech shutdown failed")


def main() -> None:
    args = parse_args()

    # --- phase 1: elevation (hosts editing needs admin; skipped in dev modes) ---
    from deepwork.blocking.admin import ensure_admin
    if not (args.smoke or args.dry_hosts) and not ensure_admin():
        sys.exit(0)                                # elevated copy takes over

    # --- phase 2: config + logging ---
    from deepwork.config import load_config_from_dotenv
    from deepwork.logging_setup import setup_logging
    cfg = load_config_from_dotenv()
    setup_logging(Path("logs"))
    if not cfg.openai_api_key:
        log.error("OPENAI_API_KEY missing - copy .env.example to .env and set it")
        sys.exit(1)

    # --- phase 3: enforcement backend (real hosts writes vs logged dry run) ---
    from deepwork.blocking.hosts_blocker import DryRunBlocker, HostsBlocker
    blocker = DryRunBlocker() if (args.dry_hosts or args.smoke) else HostsBlocker(cfg.hosts_path)

    # --- phase 4: build and wire all collaborators ---
    try:
        scheduler, flask_app, (state, store, speech) = build_app_objects(cfg, blocker)
    except ValueError as exc:
        # Invalid projects.json is configuration, so fail before any scheduler
        # threads or web requests can run with a silently weakened policy.
        log.error("configuration invalid: %s", exc)
        sys.exit(1)

    # --- phase 5: crash/exit safety — never leave the hosts file blocked ---
    # atexit runs on normal exit and unhandled exceptions (not on hard kill;
    # README documents manual cleanup): https://docs.python.org/3/library/atexit.html
    atexit.register(
        shutdown_runtime,
        scheduler,
        state,
        blocker,
        store,
        speech,
    )

    # --- phase 6: run ---
    run_mode(args, cfg, scheduler, flask_app, speech)


if __name__ == "__main__":
    main()
