# Background scheduler — the app's heartbeat. Two daemon threads:
#  * enforcer (every KILL_INTERVAL_S): kills distraction apps and acts as the
#    break watchdog that auto-restores blocking when a break expires.
#  * monitor (every CAPTURE_INTERVAL_S): capture → stitch → save → batch →
#    analyze → nudge/praise via TTS.
# Plain threads (not asyncio) because every underlying call is blocking C or
# subprocess work; loops wait on threading.Event so stop() is instant:
# https://docs.python.org/3/library/threading.html#threading.Event.wait

import logging
import threading
from datetime import datetime

from deepwork.blocking import app_killer
from deepwork.monitoring import screen_capture, stitcher, webcam_capture

log = logging.getLogger(__name__)


def capture_stitched():
    """Default capture_fn: grab all monitors + webcam, return ONE labeled image."""
    tiles = [(f"Monitor {i + 1}", img)
             for i, img in enumerate(screen_capture.capture_monitors())]
    webcam = webcam_capture.capture_webcam()       # None when unavailable
    if webcam is not None:
        tiles.append(("Webcam", webcam))
    # Caption doubles as the capture's timestamp inside the image itself.
    return stitcher.stitch(tiles, caption=f"{datetime.now():%Y-%m-%d %H:%M:%S}")


class Scheduler:
    def __init__(self, state, blocker, store, analyzer, messages, speech,
                 capture_interval_s: int, kill_interval_s: int,
                 capture_fn=None, kill_fn=None):
        # Collaborators injected — real objects in main.py, fakes in tests.
        self.state = state
        self.blocker = blocker
        self.store = store
        self.analyzer = analyzer
        self.messages = messages
        self.speech = speech
        self.capture_interval_s = capture_interval_s
        self.kill_interval_s = kill_interval_s
        self.capture_fn = capture_fn or capture_stitched
        self.kill_fn = kill_fn or app_killer.kill_targets
        # Minutes of work each verdict certifies = the whole batch window
        # (batch_size captures x interval); set properly by main.py.
        self.verdict_minutes = 25
        # Event.set() wakes every wait() immediately → instant shutdown.
        self.stop_event = threading.Event()
        self.threads: list[threading.Thread] = []

    # ---------- tick bodies (called by loops AND directly by tests) ----------

    def _enforcer_tick(self, now: datetime | None = None) -> None:
        # Sweep-kill unless everything is OFF; during BREAK the state's
        # effective list already spares explicitly allowed apps.
        from deepwork.state import Mode
        if self.state.mode is not Mode.OFF:
            self.kill_fn(self.state.effective_kill_processes())
        # Break watchdog: on expiry restore ON + full blocklist (requirement 5
        # "timed break with auto-restore").
        if self.state.end_break_if_due(now=now):
            self.blocker.apply(self.state.effective_blocklist())
            self.store.append_session_event({"event": "break_ended"})
            log.info("break expired - enforcement restored")

    def _monitor_tick(self) -> None:
        if not self.state.monitoring_active:       # only ON mode is watched
            return
        try:
            image = self.capture_fn()              # all monitors + webcam
        except Exception:                          # capture must never kill the loop
            log.exception("capture failed")
            return
        path = self.store.save_capture(image)
        verdict = self.analyzer.add_capture(path, topic=self.state.topic)
        if verdict is None:                        # batch still accumulating
            return
        # Fold the verdict into the streak; outcome may demand speech.
        self.state.last_verdict = {"productive": verdict.productive,
                                   "reason": verdict.reason,
                                   "ts": datetime.now().isoformat()}
        outcome = self.state.record_verdict(verdict.productive,
                                            minutes=self.verdict_minutes)
        self.store.append_session_event({"event": "verdict",
                                         "productive": verdict.productive,
                                         "reason": verdict.reason})
        if outcome:                                # "nudge" | "praise"
            text = self.messages.generate(outcome, topic=self.state.topic,
                                          reason=verdict.reason)
            self.speech.say(text)

    # ---------- thread plumbing ----------

    def _loop(self, tick, interval_s: int) -> None:
        # wait(timeout) sleeps but returns True instantly when stop() sets the
        # event — the standard interruptible-periodic-thread pattern:
        # https://docs.python.org/3/library/threading.html#threading.Event.wait
        while not self.stop_event.wait(interval_s):
            try:
                tick()
            except Exception:                      # a bad tick must not end the loop
                log.exception("scheduler tick failed")

    def start(self) -> None:
        self.threads = [
            threading.Thread(target=self._loop, name="enforcer", daemon=True,
                             args=(self._enforcer_tick, self.kill_interval_s)),
            threading.Thread(target=self._loop, name="monitor", daemon=True,
                             args=(self._monitor_tick, self.capture_interval_s)),
        ]
        for t in self.threads:
            t.start()
        log.info("scheduler started (kill every %ss, capture every %ss)",
                 self.kill_interval_s, self.capture_interval_s)

    def stop(self) -> None:
        self.stop_event.set()                      # wake both loops → exit
        for t in self.threads:
            t.join(timeout=5)                      # bounded wait, no hang
        log.info("scheduler stopped")
