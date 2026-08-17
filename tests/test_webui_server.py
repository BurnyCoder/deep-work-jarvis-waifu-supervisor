# Tests for loopback server startup and readiness-aware browser opening.
# Global context: the launcher must never guess when Flask is reachable or
# duplicate the UI port already parsed by the Python configuration layer.

import logging
import threading

import pytest

import deepwork.webui.server as server_module
from deepwork.webui.server import (
    launch_browser_when_ready,
    open_browser_when_ready,
    serve_dashboard,
)


class FakeClock:
    """Advance deterministic monotonic time whenever the worker retries."""

    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_status_probe_returns_after_headers_without_draining_body(monkeypatch):
    """Readiness needs an HTTP status, not a potentially slow response body."""

    events = []

    class FakeResponse:
        status = 204

        def read(self):
            raise AssertionError("readiness probe must not drain the body")

    class FakeConnection:
        def __init__(self, host, port, *, timeout):
            events.append(("connect", host, port, timeout))

        def request(self, method, path):
            events.append(("request", method, path))

        def getresponse(self):
            events.append("headers")
            return FakeResponse()

        def close(self):
            events.append("close")

    monkeypatch.setattr(server_module, "HTTPConnection", FakeConnection)

    assert server_module._probe_status("127.0.0.1", 5000, 0.75) == 204
    assert events == [
        ("connect", "127.0.0.1", 5000, 0.75),
        ("request", "GET", "/status"),
        "headers",
        "close",
    ]


def test_server_binds_configured_loopback_port_before_browser_and_serving():
    """A successful bind must precede browser launch and request handling."""

    events = []
    flask_app = object()

    class FakeServer:
        def serve_forever(self):
            events.append("serve")

        def server_close(self):
            events.append("close")

    def server_factory(host, port, app, *, threaded):
        events.append(("bind", host, port, app, threaded))
        return FakeServer()

    def browser_launcher(host, port):
        events.append(("browser", host, port))

    serve_dashboard(
        flask_app,
        8123,
        open_browser=True,
        server_factory=server_factory,
        browser_launcher=browser_launcher,
    )

    assert events == [
        ("bind", "127.0.0.1", 8123, flask_app, True),
        ("browser", "127.0.0.1", 8123),
        "serve",
        "close",
    ]


def test_browser_is_not_started_without_the_explicit_flag():
    """Normal terminal launches preserve the existing manual-open behavior."""

    class FakeServer:
        def serve_forever(self):
            pass

        def server_close(self):
            pass

    def unexpected_browser_launch(host, port):
        raise AssertionError(f"unexpected browser launch for {host}:{port}")

    serve_dashboard(
        object(),
        5000,
        open_browser=False,
        server_factory=lambda *args, **kwargs: FakeServer(),
        browser_launcher=unexpected_browser_launch,
    )


@pytest.mark.parametrize(
    "failure",
    [OSError("port already in use"), SystemExit(1)],
)
def test_bind_failure_never_launches_the_browser(failure):
    """A port conflict must remain visible without opening the wrong service."""

    launched = []

    def failed_factory(*args, **kwargs):
        raise failure

    with pytest.raises(type(failure)):
        serve_dashboard(
            object(),
            5000,
            open_browser=True,
            server_factory=failed_factory,
            browser_launcher=lambda *args: launched.append(args),
        )

    assert launched == []


def test_browser_worker_start_failure_does_not_stop_bound_server(caplog):
    """Optional browser integration cannot take down a listening dashboard."""

    events = []

    class FakeServer:
        def serve_forever(self):
            events.append("serve")

        def server_close(self):
            events.append("close")

    def failed_launcher(*args):
        raise RuntimeError("thread unavailable")

    caplog.set_level(logging.ERROR)
    serve_dashboard(
        object(),
        5000,
        open_browser=True,
        server_factory=lambda *args, **kwargs: FakeServer(),
        browser_launcher=failed_launcher,
    )

    assert events == ["serve", "close"]
    assert "could not start dashboard browser worker" in caplog.text


def test_server_exit_cancels_pending_browser_worker():
    """Server exit signals the background worker before final socket close."""

    events = []

    class FakeCancellation:
        def set(self):
            events.append("cancel")

    class FakeServer:
        def serve_forever(self):
            events.append("serve")

        def server_close(self):
            events.append("close")

    def browser_launcher(*args):
        events.append("browser")
        return FakeCancellation()

    serve_dashboard(
        object(),
        5000,
        open_browser=True,
        server_factory=lambda *args, **kwargs: FakeServer(),
        browser_launcher=browser_launcher,
    )

    assert events == ["browser", "serve", "cancel", "close"]


def test_server_socket_closes_when_serving_fails():
    """Unexpected server errors must still release the configured UI port."""

    closed = []

    class FailingServer:
        def serve_forever(self):
            raise RuntimeError("server failed")

        def server_close(self):
            closed.append(True)

    with pytest.raises(RuntimeError, match="server failed"):
        serve_dashboard(
            object(),
            5000,
            server_factory=lambda *args, **kwargs: FailingServer(),
        )

    assert closed == [True]


def test_readiness_retries_then_opens_configured_url_once(caplog):
    """Any completed HTTP response proves reachability, including an error."""

    clock = FakeClock()
    outcomes = [ConnectionRefusedError(), ConnectionResetError(), 503]
    attempts = []
    opened = []

    def probe(host, port, timeout_s):
        attempts.append((host, port, timeout_s))
        outcome = outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    caplog.set_level(logging.INFO)
    open_browser_when_ready(
        "127.0.0.1",
        8123,
        probe=probe,
        opener=lambda url: opened.append(url) or True,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        readiness_timeout_s=5.0,
        retry_interval_s=0.25,
        request_timeout_s=0.5,
    )

    assert attempts == [
        ("127.0.0.1", 8123, 0.5),
        ("127.0.0.1", 8123, 0.5),
        ("127.0.0.1", 8123, 0.5),
    ]
    assert opened == ["http://127.0.0.1:8123"]
    assert "HTTP 503" in caplog.text


def test_readiness_timeout_logs_manual_url_without_opening(caplog):
    """The worker must not recreate the original connection-refused page."""

    clock = FakeClock()
    opened = []

    caplog.set_level(logging.WARNING)
    open_browser_when_ready(
        "127.0.0.1",
        5000,
        probe=lambda *args: (_ for _ in ()).throw(ConnectionRefusedError()),
        opener=lambda url: opened.append(url) or True,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        readiness_timeout_s=0.3,
        retry_interval_s=0.1,
        request_timeout_s=0.05,
    )

    assert opened == []
    assert "readiness timed out" in caplog.text
    assert "http://127.0.0.1:5000" in caplog.text


def test_final_probe_timeout_is_clamped_to_remaining_deadline():
    """The readiness deadline cannot overrun by a full request timeout."""

    clock = FakeClock()
    attempted_timeouts = []

    def timed_out_probe(host, port, timeout_s):
        attempted_timeouts.append(timeout_s)
        clock.now += timeout_s
        raise TimeoutError("still starting")

    open_browser_when_ready(
        "127.0.0.1",
        5000,
        probe=timed_out_probe,
        opener=lambda url: True,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        readiness_timeout_s=0.25,
        retry_interval_s=0.1,
        request_timeout_s=1.0,
    )

    assert attempted_timeouts == [0.25]


def test_cancelled_readiness_worker_never_probes_or_opens():
    """Server shutdown wins over pending background browser work."""

    cancelled = threading.Event()
    cancelled.set()

    open_browser_when_ready(
        "127.0.0.1",
        5000,
        probe=lambda *args: (_ for _ in ()).throw(
            AssertionError("cancelled worker must not probe")
        ),
        opener=lambda url: (_ for _ in ()).throw(
            AssertionError("cancelled worker must not open")
        ),
        cancel_event=cancelled,
    )


@pytest.mark.parametrize("failure", [False, RuntimeError("no default browser")])
def test_browser_launch_failure_is_logged_without_escaping(failure, caplog):
    """Browser integration is optional and must never terminate the server."""

    def opener(url):
        if isinstance(failure, BaseException):
            raise failure
        return failure

    caplog.set_level(logging.WARNING)
    open_browser_when_ready(
        "127.0.0.1",
        5000,
        probe=lambda *args: 200,
        opener=opener,
    )

    assert "could not open the control panel" in caplog.text


def test_browser_worker_is_named_daemon_and_started():
    """The optional opener cannot keep shutdown alive or block serving."""

    captured = {}

    class FakeThread:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def start(self):
            captured["started"] = True

    launch_browser_when_ready(
        "127.0.0.1",
        5599,
        thread_factory=FakeThread,
    )

    assert captured["name"] == "deepwork-dashboard-browser"
    assert captured["daemon"] is True
    assert captured["args"] == ("127.0.0.1", 5599)
    assert isinstance(captured["kwargs"]["cancel_event"], threading.Event)
    assert captured["started"] is True
