# UAC elevation helper. Global context: writing to
# C:\Windows\System32\drivers\etc\hosts requires Administrator rights, so
# main.py calls ensure_admin() first — if the process isn't elevated it
# relaunches itself once through the Windows "runas" verb (one UAC prompt)
# and exits; the elevated copy then runs everything.

import ctypes   # stdlib bridge to Win32 DLLs: https://docs.python.org/3/library/ctypes.html
import logging
import sys

log = logging.getLogger(__name__)


def is_admin() -> bool:
    # shell32.IsUserAnAdmin returns nonzero when the token is elevated:
    # https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-isuseranadmin
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):  # non-Windows or DLL failure → not admin
        return False


def relaunch_as_admin() -> None:
    # ShellExecuteW with the "runas" verb shows the UAC consent dialog and
    # starts an elevated copy of this same interpreter + script + args:
    # https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-shellexecutew
    # list2cmdline re-quotes argv per Windows rules:
    # https://docs.python.org/3/library/subprocess.html#converting-an-argument-sequence-to-a-string-on-windows
    import subprocess
    params = subprocess.list2cmdline(sys.argv)
    log.info("not elevated - relaunching with UAC prompt")
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)


def ensure_admin() -> bool:
    """True if already elevated; otherwise trigger relaunch and return False
    (caller should sys.exit(0) and let the elevated copy take over)."""
    if is_admin():
        return True
    relaunch_as_admin()
    return False
