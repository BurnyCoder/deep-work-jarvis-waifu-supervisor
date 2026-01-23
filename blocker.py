"""Website blocking via Windows hosts file modification."""

import ctypes
import sys
from config import BLOCKED_SITES, HOSTS_PATH, HOSTS_MARKER_START, HOSTS_MARKER_END


def is_admin() -> bool:
    """Check if the script is running with admin privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def read_hosts_file() -> str:
    """Read the current hosts file content."""
    try:
        with open(HOSTS_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""
    except PermissionError:
        print("Error: Cannot read hosts file. Run as Administrator.")
        return ""


def write_hosts_file(content: str) -> bool:
    """Write content to the hosts file."""
    try:
        with open(HOSTS_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except PermissionError:
        print("Error: Cannot write to hosts file. Run as Administrator.")
        return False


def remove_our_entries(content: str) -> str:
    """Remove our blocking entries from hosts file content."""
    lines = content.split("\n")
    result = []
    skip = False

    for line in lines:
        if line.strip() == HOSTS_MARKER_START:
            skip = True
            continue
        if line.strip() == HOSTS_MARKER_END:
            skip = False
            continue
        if not skip:
            result.append(line)

    # Remove trailing empty lines that we might have added
    while result and result[-1].strip() == "":
        result.pop()

    return "\n".join(result)


def block_sites() -> bool:
    """Add blocked sites to the hosts file."""
    if not is_admin():
        print("Warning: Not running as admin. Website blocking may fail.")

    content = read_hosts_file()

    # First remove any existing entries from us
    content = remove_our_entries(content)

    # Build the block entries
    block_lines = [
        "",
        HOSTS_MARKER_START,
    ]
    for site in BLOCKED_SITES:
        block_lines.append(f"0.0.0.0 {site}")
    block_lines.append(HOSTS_MARKER_END)

    # Append to hosts file
    new_content = content + "\n".join(block_lines)

    if write_hosts_file(new_content):
        flush_dns()
        return True
    return False


def unblock_sites() -> bool:
    """Remove blocked sites from the hosts file."""
    content = read_hosts_file()
    new_content = remove_our_entries(content)

    if write_hosts_file(new_content):
        flush_dns()
        return True
    return False


def flush_dns():
    """Flush DNS cache to apply hosts file changes immediately."""
    import subprocess
    try:
        subprocess.run(
            ["ipconfig", "/flushdns"],
            capture_output=True,
            check=True
        )
    except Exception as e:
        print(f"Warning: Could not flush DNS cache: {e}")


def are_sites_blocked() -> bool:
    """Check if our blocking entries are present in the hosts file."""
    content = read_hosts_file()
    return HOSTS_MARKER_START in content
