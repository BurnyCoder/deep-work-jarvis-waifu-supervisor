# Hosts-file website blocker. Global context: redirecting a domain to
# loopback in the Windows hosts file redirects clients that honor that mapping:
# https://learn.microsoft.com/en-us/windows-server/networking/dns/queries-lookups
# Resolver behavior varies; Chromium's built-in resolver also reads HOSTS, so
# Secure DNS alone does not imply that hosts blocking is bypassed:
# https://chromium.googlesource.com/chromium/src/+/main/net/dns/README.md
# Our marker-fenced section is replaced/removed by rewriting the complete file;
# this is not a byte-preserving backup/restore or a network security boundary.

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
        # Read as strict UTF-8; incompatible existing encodings raise instead of
        # being silently repaired. Newline decoding follows pathlib's text I/O:
        # https://docs.python.org/3/library/pathlib.html#pathlib.Path.read_text
        return self.hosts_path.read_text(encoding="utf-8")

    def _strip_block(self, text: str) -> str:
        # Remove the first fenced section and normalize adjacent newlines. An
        # unmatched start marker consumes the remaining tail; see recovery docs.
        if START_MARK not in text:
            return text
        before, rest = text.split(START_MARK, 1)      # up to our fence
        after = rest.split(END_MARK, 1)[1] if END_MARK in rest else ""
        return before.rstrip("\n") + ("\n" if before.strip() else "") + after.lstrip("\n")

    def _flush_dns(self) -> None:
        # Request a Windows resolver-cache reset; the exit status is ignored,
        # and application caches/connections can outlive this best-effort step:
        # https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/ipconfig
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True, check=False)

    # ---------- public API ----------

    def apply(self, domains: list[str] | tuple[str, ...]) -> None:
        """Replace our fenced section with 127.0.0.1/::1 lines for `domains`."""
        with self._lock:
            base = self._strip_block(self._read())    # idempotency: start clean
            # Map each hostname in both address families without assuming which
            # a client prefers. Chromium documents both A and AAAA resolution:
            # https://chromium.googlesource.com/chromium/src/+/main/net/dns/README.md
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
        """Remove the first managed section; do not promise exact-file restoration."""
        with self._lock:
            text = self._read()
            if START_MARK not in text:                # nothing of ours → no-op
                return
            self.hosts_path.write_text(self._strip_block(text), encoding="utf-8")
            self._flush_dns()
            log.info("hosts block cleared")


class DryRunBlocker:
    """Drop-in HostsBlocker that only logs — used by `main.py --dry-hosts` so
    the whole app can be exercised WITHOUT Administrator rights (no real
    hosts-file writes). Same apply/clear interface (duck typing)."""

    def apply(self, domains) -> None:
        log.info("[dry-hosts] would block %d domains", len(tuple(domains)))

    def clear(self) -> None:
        log.info("[dry-hosts] would clear the hosts block")
