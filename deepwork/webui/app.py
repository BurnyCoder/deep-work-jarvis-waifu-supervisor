# Flask control panel. Global context: this is the ONLY user interface —
# every mode change flows through these routes, which mutate SessionState and
# re-apply/clear the hosts blocker accordingly. App-factory pattern so tests
# can build an app around fakes:
# https://flask.palletsprojects.com/en/stable/patterns/appfactories/

import logging
from datetime import datetime

# Flask quickstart: https://flask.palletsprojects.com/en/stable/quickstart/
from flask import Flask, jsonify, redirect, render_template, request

from deepwork.site_access import site_labels, site_options
from deepwork.webui.status import build_status_payload, empty_runtime_snapshot

log = logging.getLogger(__name__)


def create_app(
    state,
    blocker,
    store,
    messages,
    speech,
    runtime_snapshot=None,
    now_fn=None,
) -> Flask:
    app = Flask(__name__)                          # templates/ auto-discovered
    # Optional providers preserve the app factory's dependency-injected tests.
    get_runtime_snapshot = runtime_snapshot or empty_runtime_snapshot
    get_now = now_fn or datetime.now

    @app.get("/")
    def index():
        # Jinja template gets the topic history for the <datalist> dropdown
        # and current mode for display:
        # https://flask.palletsprojects.com/en/stable/quickstart/#rendering-templates
        projects = [
            {
                "name": name,
                "sites": list(site_labels(state.project_allowlists[name])),
            }
            for name in sorted(state.project_allowlists)
        ]
        return render_template(
            "index.html",
            topics=state.previous_topics,
            mode=state.mode.value,
            projects=projects,
            site_options=site_options(),
        )

    @app.post("/start")
    def start():
        # Requirement 4/5: entering a topic starts ON mode; one-off site
        # choices and an optional saved preset open only what the task needs.
        form = request.form
        topic = form["topic"].strip()
        project = form.get("project") or None
        selected_sites = form.getlist("allowed_sites")
        agentic = form.get("agentic") == "on"
        try:
            # Same-name checkbox values are retrieved with MultiDict.getlist:
            # https://werkzeug.palletsprojects.com/en/stable/datastructures/#werkzeug.datastructures.MultiDict.getlist
            state.start_session(
                topic,
                now=get_now(),
                allowed_sites=selected_sites,
                project=project,
                agentic=agentic,
            )
        except ValueError as exc:
            # Browser constraints are UX only; reject forged values before a
            # hosts write, state change, event, prompt, or spoken response.
            log.warning("session start refused: %s", exc)
            return str(exc), 400
        blocker.apply(state.effective_blocklist()) # enforce immediately
        allowed_sites = list(state.work_allowed_sites)
        store.append_session_event({
            "event": "session_start",
            "topic": topic,
            "project": state.active_project,
            "selected_sites": list(state.task_allowed_sites),
            "allowed_sites": allowed_sites,
            "agentic": state.agentic_mode,
        })
        store.save_state(state.to_dict())          # topic history survives restart
        log.info(
            "session started: topic=%r project=%r selected_sites=%s "
            "allowed_sites=%s agentic=%s",
            topic,
            state.active_project,
            list(state.task_allowed_sites),
            allowed_sites,
            state.agentic_mode,
        )
        # LLM writes the good-luck line, TTS speaks it ("good luck on x topic").
        speech.say(messages.generate("good_luck", topic=topic,
                                     session_context=state.context_summary()))
        return redirect("/")

    @app.post("/break")
    def take_break():
        # Requirement 5: user states purpose + duration + kind; allowances are
        # comma-separated site/app group names (e.g. "reddit,discord").
        form = request.form
        split = lambda s: [x.strip() for x in s.split(",") if x.strip()]
        ok, reason = state.start_break(
            purpose=form["purpose"], minutes=int(form["minutes"]),
            kind=form.get("kind", "away"),
            allowed_sites=split(form.get("allowed_sites", "")),
            allowed_apps=split(form.get("allowed_apps", "")),
            now=get_now(),
        )
        if not ok:                                 # e.g. social cap exhausted
            log.info("break refused: %s", reason)
            return reason, 400
        blocker.apply(state.effective_blocklist()) # unblock allowed sites only
        store.append_session_event({"event": "break_start", **form.to_dict()})
        store.save_state(state.to_dict())          # allowance usage survives restart
        # TTS confirms the break plan back to the user (spec: "TTS responds").
        speech.say(messages.generate("break_ack", purpose=form["purpose"],
                                     minutes=form["minutes"],
                                     session_context=state.context_summary()))
        return redirect("/")

    @app.post("/break/stop")
    def stop_break():
        # A state-changing form uses POST; redirecting afterward prevents a
        # browser refresh from presenting a resubmission prompt:
        # https://flask.palletsprojects.com/en/stable/quickstart/#redirects-and-errors
        stopped_at = get_now()
        result = state.stop_break(now=stopped_at)
        if result is None:
            # The watchdog can expire a break between the dashboard poll and
            # this click. A harmless redirect is friendlier than a race-only
            # error page and does not repeat any side effect.
            log.info("break stop ignored - no active break")
            return redirect("/")

        blocker.apply(state.effective_blocklist()) # close break-only sites now
        event = {
            "event": "break_stopped",
            "purpose": result.purpose,
            "kind": result.kind,
            "requested_minutes": result.requested_minutes,
            "elapsed_seconds": result.elapsed_seconds,
            "charged_minutes": result.charged_minutes,
            "refunded_minutes": result.refunded_minutes,
        }
        store.append_session_event(event)
        store.save_state(state.to_dict())          # persist any social refund
        log.info(
            "break stopped - purpose=%r kind=%s elapsed_seconds=%d "
            "charged_minutes=%d refunded_minutes=%d; enforcement restored",
            result.purpose,
            result.kind,
            result.elapsed_seconds,
            result.charged_minutes,
            result.refunded_minutes,
        )
        try:
            # Enforcement must stay restored if the optional model call fails.
            text = messages.generate(
                "break_end_ack",
                purpose=result.purpose,
                charged_minutes=result.charged_minutes,
                session_context=state.context_summary(now=stopped_at),
            )
            speech.say(text)
        except Exception:
            log.exception("break-stop spoken feedback failed")
        return redirect("/")

    @app.post("/agentic")
    def toggle_agentic():
        # Mid-session toggle for agentic mode; re-apply blocking right away
        # (turning it OFF while the agent was busy must re-block instantly).
        state.set_agentic(request.form.get("enabled") == "on")
        blocker.apply(state.effective_blocklist())
        store.append_session_event({"event": "agentic_toggle",
                                    "enabled": state.agentic_mode})
        return redirect("/")

    @app.post("/disable")
    def disable():
        # Requirement 6: exact confirmation phrase or a hard 403.
        if not state.try_disable(request.form.get("phrase", ""), now=get_now()):
            return "Wrong confirmation phrase - enforcement stays on.", 403
        blocker.clear()                            # restore the hosts file
        store.append_session_event({"event": "disabled"})
        return redirect("/")

    @app.get("/status")
    def status():
        # Polled by index.html's JS every few seconds; also handy for curl.
        payload = build_status_payload(
            state,
            runtime_snapshot=get_runtime_snapshot,
            now=get_now(),
        )
        response = jsonify(payload)
        # Realtime status must never be reused from an intermediary cache:
        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control
        response.headers["Cache-Control"] = "no-store"
        return response

    return app
