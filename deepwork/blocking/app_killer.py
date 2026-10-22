# Distraction-app killer. Global context: the enforcer thread calls
# kill_targets() on each active tick with state.effective_kill_processes(),
# requesting termination of exact-name targets not spared by the current
# task/preset, goal, or break scopes. Timing also depends on tick duration and
# process permissions; the sweep does not wait for termination to complete.
# psutil docs: https://psutil.readthedocs.io/en/latest/

import logging

import psutil

log = logging.getLogger(__name__)


def kill_targets(process_names: list[str] | tuple[str, ...]) -> list[str]:
    """Request termination of case-insensitive exact-name matches; return names
    whose kill() calls succeeded, without waiting to confirm process exit."""
    # Pre-lowercase the target set once — one readable line per the spec's
    # "can it be one readable line" checklist.
    targets = {name.lower() for name in process_names}
    if not targets:
        return []
    killed: list[str] = []
    # process_iter(["name"]) pre-fetches each process's name into proc.info;
    # processes can still disappear or deny access before the kill call:
    # https://psutil.readthedocs.io/en/latest/#psutil.process_iter
    for proc in psutil.process_iter(["name"]):
        try:
            name = proc.info.get("name") or ""
            if name.lower() in targets:
                # Windows TerminateProcess initiates asynchronous termination:
                # https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-terminateprocess
                proc.kill()                       # No wait() confirms actual exit.
                killed.append(name)
        # Documented races: process already gone, or protected by the OS —
        # both must be survived silently in a periodic sweep:
        # https://psutil.readthedocs.io/en/latest/#psutil.NoSuchProcess
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    if killed:
        log.info("termination requested for distraction apps: %s", ", ".join(killed))
    return killed
