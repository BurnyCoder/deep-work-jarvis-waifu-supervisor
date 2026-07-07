# Flask control panel. Global context: this is the ONLY user interface —
# every mode change flows through these routes, which mutate SessionState and
# re-apply/clear the hosts blocker accordingly. App-factory pattern so tests
# can build an app around fakes:
# https://flask.palletsprojects.com/en/stable/patterns/appfactories/

import logging

# Flask quickstart: https://flask.palletsprojects.com/en/stable/quickstart/
from flask import Flask, jsonify, redirect, render_template, request

log = logging.getLogger(__name__)


def create_app(state, blocker, store, messages, speech) -> Flask:
    app = Flask(__name__)                          # templates/ auto-discovered

    @app.get("/")
    def index():
        # Jinja template gets the topic history for the <datalist> dropdown
        # and current mode for display:
        # https://flask.palletsprojects.com/en/stable/quickstart/#rendering-templates
        return render_template("index.html",
                               topics=state.previous_topics,
                               mode=state.mode.value,
                               projects=sorted(state.project_allowlists))

    @app.post("/start")
    def start():
        # Requirement 4/5: entering a topic starts ON mode; optional project
        # activates its social allowlist while everything else stays blocked.
        topic = request.form["topic"].strip()
        state.start_session(topic)
        state.set_project(request.form.get("project") or None)
        blocker.apply(state.effective_blocklist()) # enforce immediately
        store.append_session_event({"event": "session_start", "topic": topic})
        # LLM writes the good-luck line, TTS speaks it ("good luck on x topic").
        speech.say(messages.generate("good_luck", topic=topic))
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
        )
        if not ok:                                 # e.g. social cap exhausted
            log.info("break refused: %s", reason)
            return reason, 400
        blocker.apply(state.effective_blocklist()) # unblock allowed sites only
        store.append_session_event({"event": "break_start", **form.to_dict()})
        # TTS confirms the break plan back to the user (spec: "TTS responds").
        speech.say(messages.generate("break_ack", purpose=form["purpose"],
                                     minutes=form["minutes"]))
        return redirect("/")

    @app.post("/disable")
    def disable():
        # Requirement 6: exact confirmation phrase or a hard 403.
        if not state.try_disable(request.form.get("phrase", "")):
            return "Wrong confirmation phrase - enforcement stays on.", 403
        blocker.clear()                            # restore the hosts file
        store.append_session_event({"event": "disabled"})
        return redirect("/")

    @app.get("/status")
    def status():
        # Polled by index.html's JS every few seconds; also handy for curl.
        br = state.current_break
        return jsonify({
            "mode": state.mode.value,
            "topic": state.topic,
            "productive_streak_min": state.productive_streak_min,
            "social_minutes_remaining": state.social_minutes_remaining(),
            "last_verdict": state.last_verdict,
            "break": {"purpose": br.purpose, "kind": br.kind,
                      "until": br.end_time.isoformat()} if br else None,
        })

    return app
