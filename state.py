"""App state management for ON/OFF/BREAK modes."""

import threading
import time
from enum import Enum
from typing import Optional, Callable


class Mode(Enum):
    ON = "on"
    OFF = "off"
    BREAK = "break"


class AppState:
    def __init__(self):
        self._mode = Mode.OFF
        self._lock = threading.Lock()
        self._break_timer: Optional[threading.Timer] = None
        self._break_end_time: Optional[float] = None
        self._on_mode_change: Optional[Callable[[Mode], None]] = None

    @property
    def mode(self) -> Mode:
        with self._lock:
            return self._mode

    @property
    def break_remaining_seconds(self) -> int:
        """Returns remaining break time in seconds, or 0 if not on break."""
        with self._lock:
            if self._mode != Mode.BREAK or self._break_end_time is None:
                return 0
            remaining = self._break_end_time - time.time()
            return max(0, int(remaining))

    def set_on_mode_change(self, callback: Callable[[Mode], None]):
        """Set callback to be called when mode changes."""
        self._on_mode_change = callback

    def set_mode(self, new_mode: Mode, break_duration_minutes: int = 5) -> bool:
        """
        Change the app mode.

        Args:
            new_mode: The mode to switch to
            break_duration_minutes: Duration for BREAK mode (ignored for other modes)

        Returns:
            True if mode was changed successfully
        """
        with self._lock:
            # Cancel any existing break timer
            if self._break_timer is not None:
                self._break_timer.cancel()
                self._break_timer = None
                self._break_end_time = None

            old_mode = self._mode
            self._mode = new_mode

            # Set up break timer if entering break mode
            if new_mode == Mode.BREAK:
                duration_seconds = break_duration_minutes * 60
                self._break_end_time = time.time() + duration_seconds
                self._break_timer = threading.Timer(
                    duration_seconds,
                    self._end_break
                )
                self._break_timer.daemon = True
                self._break_timer.start()

        # Notify callback outside of lock
        if old_mode != new_mode and self._on_mode_change:
            self._on_mode_change(new_mode)

        return True

    def _end_break(self):
        """Called when break timer expires - switches back to ON mode."""
        with self._lock:
            self._break_timer = None
            self._break_end_time = None
            if self._mode == Mode.BREAK:
                self._mode = Mode.ON

        if self._on_mode_change:
            self._on_mode_change(Mode.ON)

    def is_blocking_enabled(self) -> bool:
        """Returns True if website blocking should be active."""
        return self.mode == Mode.ON

    def is_monitoring_enabled(self) -> bool:
        """Returns True if screenshot monitoring should be active."""
        return self.mode == Mode.ON


# Global app state instance
app_state = AppState()
