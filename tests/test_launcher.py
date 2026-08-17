# Regression tests for the Windows double-click launcher.
# Global context: startup timing and the configured UI port belong to Python,
# while the batch file owns only elevation, dependency checks, and opt-in UX.

from pathlib import Path


def test_launcher_delegates_browser_opening_without_timing_or_port_guesses():
    launcher = Path("Start Deep Work.bat").read_text(encoding="utf-8")
    normalized = launcher.lower()

    assert "uv run python main.py --open-browser" in launcher
    assert "timeout /t" not in normalized
    assert "127.0.0.1:5599" not in normalized
