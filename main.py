# Deep Work — top-level wrapper. This file is deliberately a table of
# contents: each phase below is one clearly-named function from a module that
# hides its implementation details (project rule: "one abstracted wrapper
# file that calls different clearly named readable phases").
# Run:  uv run python main.py            (full app, asks for UAC elevation)
#       uv run python main.py --smoke    (one capture→analyze→speak cycle, no admin)
#       uv run python main.py --dry-hosts (full app, hosts writes only logged)

import argparse
import atexit
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    # argparse stdlib CLI parsing: https://docs.python.org/3/library/argparse.html
    p = argparse.ArgumentParser(description="Deep Work productivity enforcement")
    p.add_argument("--smoke", action="store_true",
                   help="run one capture/analyze/speak cycle and exit (no admin needed)")
    p.add_argument("--dry-hosts", action="store_true",
                   help="run everything but only LOG hosts-file changes (no admin needed)")
    return p.parse_args()


def build_app_objects(cfg, blocker):
    """Construct and wire every collaborator; returns (scheduler, flask_app, extras)."""
    # Imports live here so `--help` stays instant and import order is explicit.
    from openai import OpenAI                      # https://github.com/openai/openai-python

    from deepwork.feedback.messages import MessageGenerator
    from deepwork.feedback.tts import SpeechQueue, make_speaker
    from deepwork.monitoring.analyzer import AgentActivityChecker, ProductivityAnalyzer
    from deepwork.scheduler import Scheduler
    from deepwork.state import SessionState
    from deepwork.storage import ResultsStore
    from deepwork.webui.app import create_app

    store = ResultsStore(Path("results"))          # requirement 8: results folder
    state = SessionState(daily_social_cap_min=cfg.daily_social_cap_min,
                         project_allowlists=load_project_allowlists())
    state.load_dict(store.load_state())            # allowance/topics survive restarts

    client = OpenAI(api_key=cfg.openai_api_key)    # one shared API client
    analyzer = ProductivityAnalyzer(client=client, model=cfg.vision_model,
                                    store=store, batch_size=cfg.batch_size)
    messages = MessageGenerator(client=client, model=cfg.text_model, store=store)
    speech = SpeechQueue(make_speaker(cfg, client))

    scheduler = Scheduler(state=state, blocker=blocker, store=store,
                          analyzer=analyzer, messages=messages, speech=speech,
                          capture_interval_s=cfg.capture_interval_s,
                          kill_interval_s=cfg.kill_interval_s,
                          # Agentic mode watcher: fast single-capture polls.
                          agent_checker=AgentActivityChecker(
                              client=client, model=cfg.vision_model, store=store),
                          agent_check_interval_s=cfg.agent_check_interval_s)
    # One verdict certifies the whole batch window, in minutes.
    scheduler.verdict_minutes = max(1, cfg.batch_size * cfg.capture_interval_s // 60)

    flask_app = create_app(state=state, blocker=blocker, store=store,
                           messages=messages, speech=speech)
    return scheduler, flask_app, (state, store, speech)


def load_project_allowlists() -> dict:
    # Optional projects.json maps project name -> allowed site groups, e.g.
    # {"ml-research": ["twitter"]} (requirement 5, per-project allowlist).
    import json
    path = Path("projects.json")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def run_smoke(scheduler, speech) -> None:
    """One immediate capture→stitch→analyze→speak cycle for manual verification
    (documented in README) — forces batch size 1 so the vision call happens now."""
    scheduler.analyzer.batch_size = 1
    scheduler.state.start_session("smoke test")
    scheduler._monitor_tick()                      # the real pipeline, once
    verdict = scheduler.state.last_verdict or {}
    # Speak the verdict reason so TTS is exercised end-to-end too.
    speech.say(f"Smoke test verdict: {'productive' if verdict.get('productive') else 'not productive'}. "
               f"{verdict.get('reason', 'no verdict')}")
    speech.wait_idle(timeout=60)
    log.info("smoke cycle complete: %s", verdict)


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
    scheduler, flask_app, (state, store, speech) = build_app_objects(cfg, blocker)

    # --- phase 5: crash/exit safety — never leave the hosts file blocked ---
    # atexit runs on normal exit and unhandled exceptions (not on hard kill;
    # README documents manual cleanup): https://docs.python.org/3/library/atexit.html
    atexit.register(lambda: (scheduler.stop(), blocker.clear(),
                             store.save_state(state.to_dict()), speech.stop()))

    # --- phase 6: run ---
    if args.smoke:
        run_smoke(scheduler, speech)
        return
    scheduler.start()                              # enforcer + monitor threads
    log.info("control panel: http://127.0.0.1:%d", cfg.ui_port)
    # Flask dev server is fine for a localhost-only panel; threaded=True lets
    # status polls overlap form posts:
    # https://flask.palletsprojects.com/en/stable/api/#flask.Flask.run
    flask_app.run(host="127.0.0.1", port=cfg.ui_port, threaded=True)


if __name__ == "__main__":
    main()
