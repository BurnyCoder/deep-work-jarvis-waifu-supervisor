# Loopback dashboard server and readiness-aware browser opening.
# Global context: Python owns the parsed UI port and the listening socket, so
# the Windows launcher never guesses a startup delay or duplicates `.env`.

from collections.abc import Callable
from http.client import HTTPConnection, HTTPException
import logging
import threading
import time
import webbrowser

from werkzeug.serving import make_server


log = logging.getLogger(__name__)

LOOPBACK_HOST = "127.0.0.1"
READINESS_PATH = "/status"
READINESS_TIMEOUT_S = 30.0
READINESS_RETRY_INTERVAL_S = 0.2
READINESS_REQUEST_TIMEOUT_S = 1.0


def _dashboard_url(host: str, port: int) -> str:
    """Return the one canonical loopback URL shown in logs and the browser."""

    return f"http://{host}:{port}"


def _probe_status(host: str, port: int, timeout_s: float) -> int:
    """Return `/status`'s HTTP code once the local server answers a request."""

    # HTTPConnection verifies application-level reachability rather than only
    # a listening TCP socket: https://docs.python.org/3/library/http.client.html
    connection = HTTPConnection(host, port, timeout=timeout_s)
    try:
        connection.request("GET", READINESS_PATH)
        response = connection.getresponse()
        # Headers and the status line already prove Flask answered. Do not
        # drain a body that could extend beyond the monotonic readiness budget.
        return response.status
    finally:
        connection.close()


def open_browser_when_ready(
    host: str,
    port: int,
    *,
    probe: Callable[[str, int, float], int] = _probe_status,
    opener: Callable[[str], bool] = webbrowser.open_new_tab,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    readiness_timeout_s: float = READINESS_TIMEOUT_S,
    retry_interval_s: float = READINESS_RETRY_INTERVAL_S,
    request_timeout_s: float = READINESS_REQUEST_TIMEOUT_S,
    cancel_event: threading.Event | None = None,
) -> None:
    """Wait for one HTTP response, then open one default-browser tab."""

    dashboard_url = _dashboard_url(host, port)
    status_url = f"{dashboard_url}{READINESS_PATH}"
    # monotonic() cannot move backward when the system clock is corrected:
    # https://docs.python.org/3/library/time.html#time.monotonic
    deadline = monotonic() + readiness_timeout_s
    log.info("waiting for dashboard readiness: %s", status_url)
    last_error: BaseException | None = None

    while True:
        if cancel_event is not None and cancel_event.is_set():
            log.info("dashboard browser opening cancelled: %s", dashboard_url)
            return
        remaining_s = deadline - monotonic()
        if remaining_s <= 0:
            log.warning(
                "dashboard readiness timed out after %.1f seconds; "
                "open manually: %s (last error: %s)",
                readiness_timeout_s,
                dashboard_url,
                last_error or "none",
            )
            return
        try:
            # Any HTTP status proves Flask can answer; a non-2xx response is
            # still opened so an application error remains visible to users.
            status = probe(host, port, min(request_timeout_s, remaining_s))
            break
        except (OSError, HTTPException) as exc:
            last_error = exc
            remaining_s = deadline - monotonic()
            if remaining_s <= 0:
                log.warning(
                    "dashboard readiness timed out after %.1f seconds; "
                    "open manually: %s (last error: %s)",
                    readiness_timeout_s,
                    dashboard_url,
                    exc,
                )
                return
            retry_wait_s = min(retry_interval_s, remaining_s)
            if cancel_event is not None:
                if cancel_event.wait(retry_wait_s):
                    log.info(
                        "dashboard browser opening cancelled: %s",
                        dashboard_url,
                    )
                    return
            else:
                sleep(retry_wait_s)

    log.info("dashboard ready: %s returned HTTP %d", status_url, status)
    if cancel_event is not None and cancel_event.is_set():
        log.info("dashboard browser opening cancelled: %s", dashboard_url)
        return
    try:
        # open_new_tab delegates to the OS default browser and reports whether
        # launch succeeded: https://docs.python.org/3/library/webbrowser.html
        opened = opener(dashboard_url)
    except Exception:
        log.exception(
            "could not open the control panel; open manually: %s",
            dashboard_url,
        )
        return
    if not opened:
        log.warning(
            "could not open the control panel; open manually: %s",
            dashboard_url,
        )
        return
    log.info("opened control panel in the default browser: %s", dashboard_url)


def launch_browser_when_ready(
    host: str,
    port: int,
    *,
    thread_factory: Callable[..., threading.Thread] = threading.Thread,
) -> threading.Event:
    """Start the optional readiness/browser work without blocking serving."""

    # A daemon is appropriate because browser launch is optional UX and must
    # never keep normal shutdown alive after the server stops:
    # https://docs.python.org/3/library/threading.html#thread-objects
    cancel_event = threading.Event()
    worker = thread_factory(
        target=open_browser_when_ready,
        args=(host, port),
        kwargs={"cancel_event": cancel_event},
        name="deepwork-dashboard-browser",
        daemon=True,
    )
    worker.start()
    return cancel_event


def serve_dashboard(
    flask_app,
    port: int,
    *,
    open_browser: bool = False,
    server_factory: Callable[..., object] = make_server,
    browser_launcher: Callable[[str, int], threading.Event | None] = (
        launch_browser_when_ready
    ),
) -> None:
    """Bind the threaded loopback server, optionally open it, and serve."""

    # Werkzeug documents make_server as the separately usable factory behind
    # run_simple. Its constructor binds and activates before returning, so a
    # failed/occupied port cannot start the browser worker:
    # https://github.com/pallets/werkzeug/blob/3.1.8/src/werkzeug/serving.py
    server = server_factory(
        LOOPBACK_HOST,
        port,
        flask_app,
        threaded=True,
    )
    dashboard_url = _dashboard_url(LOOPBACK_HOST, port)
    log.info("control panel listening: %s", dashboard_url)
    browser_cancel: threading.Event | None = None
    try:
        if open_browser:
            try:
                browser_cancel = browser_launcher(LOOPBACK_HOST, port)
            except Exception:
                # A missing/default-browser integration is not a server fault.
                log.exception(
                    "could not start dashboard browser worker; "
                    "open manually: %s",
                    dashboard_url,
                )
        server.serve_forever()
    finally:
        if browser_cancel is not None:
            browser_cancel.set()
        # Explicit close also protects injected/custom factories even though
        # Werkzeug's current serve_forever implementation closes on return.
        server.server_close()
