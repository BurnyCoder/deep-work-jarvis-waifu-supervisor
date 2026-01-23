"""Process killing for distraction apps."""

import threading
import time
import psutil
from config import BLOCKED_APPS
from state import app_state, Mode


class AppKiller:
    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        self._check_interval = 2  # Check every 2 seconds

    def start(self):
        """Start the app killer background thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._kill_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the app killer background thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def _kill_loop(self):
        """Main loop that continuously checks and kills blocked apps."""
        while self._running:
            if app_state.mode == Mode.ON:
                self._kill_blocked_apps()
            time.sleep(self._check_interval)

    def _kill_blocked_apps(self):
        """Find and kill all blocked app processes."""
        killed = []
        try:
            for proc in psutil.process_iter(['name', 'pid']):
                try:
                    proc_name = proc.info['name']
                    if proc_name and proc_name.lower() in [app.lower() for app in BLOCKED_APPS]:
                        proc.kill()
                        killed.append(proc_name)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        except Exception as e:
            print(f"Error in app killer: {e}")

        if killed:
            print(f"Killed apps: {', '.join(killed)}")

        return killed

    def kill_once(self) -> list[str]:
        """Kill blocked apps once (non-continuous). Returns list of killed app names."""
        return self._kill_blocked_apps()


# Global app killer instance
app_killer = AppKiller()
