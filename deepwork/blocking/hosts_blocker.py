# Hosts-file website blocker. Global context: redirecting a domain to
# 127.0.0.1 in the Windows hosts file makes every browser/app resolve it to
# the local machine, where nothing answers — the classic OS-level block
# (https://www.howtogeek.com/784196/how-to-edit-the-hosts-file-on-windows-10-or-11/).
# Our entries live inside a marker-fenced section so apply() is idempotent
# and clear() surgically restores the user's own lines.
# Known bypass documented in README: browser "Secure DNS" (DoH) skips the OS
# resolver entirely and must be disabled for hosts blocking to work.

import logging
import subprocess
import threading
from pathlib import Path

log = logging.getLogger(__name__)

# Fence markers — anything between them is ours to rewrite/delete.
START_MARK = "# >>> deepwork block start"
END_MARK = "# <<< deepwork block end"


class HostsBlocker:
    def __init__(self, hosts_path: str | Path):
        # Path injected: production passes the real Windows hosts path,
        # tests pass a pytest tmp_path file (dependency injection for IO).
        self.hosts_path = Path(hosts_path)
        # One lock so concurrent state transitions (break start + watchdog
        # expiry) can never interleave read-modify-write cycles.
        self._lock = threading.Lock()

    # ---------- internal helpers ----------

    def _read(self) -> str:
        # utf-8 tolerates comments with any characters; hosts is ASCII in
        # practice (https://docs.python.org/3/library/pathlib.html#pathlib.Path.read_text)
        return self.hosts_path.read_text(encoding="utf-8")

    def _strip_block(self, text: str) -> str:
        # Remove a previous fenced section if present. Splitting on the
        # markers is simpler and safer than regex over user content.
        if START_MARK not in text:
            return text
        before, rest = text.split(START_MARK, 1)      # up to our fence
        after = rest.split(END_MARK, 1)[1] if END_MARK in rest else ""
        return before.rstrip("\n") + ("\n" if before.strip() else "") + after.lstrip("\n")

    def _flush_dns(self) -> None:
        # Windows caches DNS answers; flush so blocks/unblocks take effect
        # immediately: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/ipconfig
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True, check=False)

    # ---------- public API ----------

    def apply(self, domains: list[str] | tuple[str, ...]) -> None:
        """Replace our fenced section with 127.0.0.1/::1 lines for `domains`."""
        with self._lock:
            base = self._strip_block(self._read())    # idempotency: start clean
            # Both A (IPv4) and AAAA (IPv6) shapes per domain — modern stacks
            # try IPv6 first (https://www.currentware.com/blog/how-to-block-websites-using-hosts-file/)
            lines = [START_MARK]
            for d in domains:
                lines.append(f"127.0.0.1 {d}")
                lines.append(f"::1 {d}")
            lines.append(END_MARK)
            new_text = base.rstrip("\n") + "\n" + "\n".join(lines) + "\n"
            self.hosts_path.write_text(new_text, encoding="utf-8")
            self._flush_dns()
            log.info("hosts block applied: %d domains", len(domains))

    def clear(self) -> None:
        """Remove our fenced section entirely, restoring the original file."""
        with self._lock:
            text = self._read()
            if START_MARK not in text:                # nothing of ours → no-op
                return
            self.hosts_path.write_text(self._strip_block(text), encoding="utf-8")
            self._flush_dns()
            log.info("hosts block cleared")
