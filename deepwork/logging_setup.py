# Dual-destination logging: every event goes to a timestamped file in logs/
# AND to the terminal in real time. Application prompts and returned response
# objects flow through this root logger uncut; a call that raises before returning
# a response can only contribute the exception information available to the app.
# Pattern: https://docs.python.org/3/howto/logging-cookbook.html#logging-to-multiple-destinations

import logging
# datetime supplies a whole-second filename stamp. Independent setup calls in
# the same second can select the same append-mode file:
# https://docs.python.org/3/library/datetime.html#datetime.datetime.strftime
from datetime import datetime
from pathlib import Path

# Shared line format: ISO-like timestamp, level, logger name, message —
# %(asctime)s et al. documented at
# https://docs.python.org/3/library/logging.html#logrecord-attributes
_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

# Marker attribute set on handlers we install, so repeat calls can find and
# replace ours without disturbing pytest's own capture handlers.
_MARKER = "_deepwork_handler"


def setup_logging(logs_dir: Path) -> Path:
    """Configure the root logger with file + terminal handlers; return the log file path.

    Idempotent: calling again removes previously-installed deepwork handlers
    first, so repeated setup does not duplicate this app's handlers (see
    https://docs.python.org/3/howto/logging.html#handlers).
    """
    # mkdir -p equivalent: https://docs.python.org/3/library/pathlib.html#pathlib.Path.mkdir
    logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    # Select a whole-second path, e.g. deepwork_20260707_221530.log. FileHandler
    # opens in append mode, so same-second setup calls can intentionally share it:
    # https://docs.python.org/3/library/logging.handlers.html#logging.FileHandler
    log_file = logs_dir / f"deepwork_{datetime.now():%Y%m%d_%H%M%S}.log"

    root = logging.getLogger()               # root logger catches all modules
    root.setLevel(logging.INFO)              # INFO = normal operational detail

    # Drop only OUR old handlers (marked below) — leaves foreign handlers alone.
    for h in [h for h in root.handlers if getattr(h, _MARKER, False)]:
        root.removeHandler(h)                # detach…
        h.close()                            # …and release the file handle

    # Python uses UTF-8 for Windows console devices, while redirected streams
    # can use a locale encoding. Explicit UTF-8 keeps our terminal/pipe logging
    # consistent: https://docs.python.org/3.13/library/sys.html#sys.stdin
    import sys
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    formatter = logging.Formatter(_FORMAT)   # shared by both destinations
    # utf-8 so LLM output with any unicode logs without UnicodeEncodeError:
    # https://docs.python.org/3/library/logging.handlers.html#logging.FileHandler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    stream_handler = logging.StreamHandler() # stderr → visible in terminal
    for handler in (file_handler, stream_handler):
        handler.setFormatter(formatter)      # same timestamped line format
        setattr(handler, _MARKER, True)      # tag as ours for idempotency
        root.addHandler(handler)             # activate destination

    logging.getLogger(__name__).info("logging to %s", log_file)
    return log_file
