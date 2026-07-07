# Distraction-app killer. Global context: the enforcer thread calls
# kill_targets() every few seconds with state.effective_kill_processes(),
# so Discord/Telegram/Steam die within seconds of launching (requirement 2)
# unless the current break explicitly allows them.
# psutil docs: https://psutil.readthedocs.io/en/latest/

import logging

import psutil

log = logging.getLogger(__name__)


def kill_targets(process_names: list[str] | tuple[str, ...]) -> list[str]:
    """Kill every running process whose name matches (case-insensitive);
    return the names actually killed this sweep."""
    # Pre-lowercase the target set once — one readable line per the spec's
    # "can it be one readable line" checklist.
    targets = {name.lower() for name in process_names}
    if not targets:
        return []
    killed: list[str] = []
    # process_iter(["name"]) pre-fetches each process's name into proc.info,
    # the documented fast-and-race-safe iteration pattern:
    # https://psutil.readthedocs.io/en/latest/#psutil.process_iter
    for proc in psutil.process_iter(["name"]):
        try:
            name = proc.info.get("name") or ""
            if name.lower() in targets:
                proc.kill()                       # SIGKILL/TerminateProcess
                killed.append(name)
        # Documented races: process already gone, or protected by the OS —
        # both must be survived silently in a periodic sweep:
        # https://psutil.readthedocs.io/en/latest/#psutil.NoSuchProcess
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    if killed:
        log.info("killed distraction apps: %s", ", ".join(killed))
    return killed
