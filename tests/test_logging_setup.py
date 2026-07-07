# Tests for deepwork/logging_setup.py — dual-destination (file + terminal)
# timestamped logging required by the project spec ("comprehensible
# timestamped logging ... to logs file and terminal realtime").
# Cookbook pattern under test:
# https://docs.python.org/3/howto/logging-cookbook.html#logging-to-multiple-destinations

import logging

from deepwork.logging_setup import setup_logging


def test_creates_log_file_and_writes_timestamped_lines(tmp_path):
    # tmp_path is pytest's per-test temporary directory fixture:
    # https://docs.pytest.org/en/stable/how-to/tmp_path.html
    log_file = setup_logging(tmp_path)
    logging.getLogger("deepwork.test").info("hello focus")
    # FileHandler opens with delay-less default, so the line is on disk after
    # the emit; read it back and check content + a timestamp prefix.
    text = log_file.read_text(encoding="utf-8")
    assert "hello focus" in text
    line = next(l for l in text.splitlines() if "hello focus" in l)
    # asctime default format starts "YYYY-MM-DD HH:MM:SS"
    # (https://docs.python.org/3/library/logging.html#logging.LogRecord)
    assert line[:4].isdigit() and line[4] == "-"


def test_idempotent_no_duplicate_handlers(tmp_path):
    # Calling setup twice (e.g. app restart within one process, or tests)
    # must not stack handlers, or every line would print twice — a classic
    # logging pitfall (https://docs.python.org/3/howto/logging.html#handlers)
    setup_logging(tmp_path)
    log_file = setup_logging(tmp_path)
    logging.getLogger("deepwork.test").info("only once")
    text = log_file.read_text(encoding="utf-8")
    assert text.count("only once") == 1
