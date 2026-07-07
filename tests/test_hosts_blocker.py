# Tests for deepwork/blocking/hosts_blocker.py — the blocker takes the hosts
# path as a constructor argument, so tests point it at a pytest tmp_path file
# and NEVER touch C:\Windows\System32\drivers\etc\hosts.
# tmp_path fixture: https://docs.pytest.org/en/stable/how-to/tmp_path.html

from deepwork.blocking.hosts_blocker import END_MARK, START_MARK, HostsBlocker

ORIGINAL = "# my corporate entries\n10.0.0.5 intranet.local\n"


def make_blocker(tmp_path, monkeypatch):
    # Silence the real `ipconfig /flushdns` subprocess during tests by
    # replacing it with a recorder (monkeypatch:
    # https://docs.pytest.org/en/stable/how-to/monkeypatch.html)
    hosts = tmp_path / "hosts"
    hosts.write_text(ORIGINAL, encoding="utf-8")
    blocker = HostsBlocker(hosts_path=hosts)
    calls = []
    monkeypatch.setattr(blocker, "_flush_dns", lambda: calls.append(1))
    return blocker, hosts, calls


def test_apply_appends_fenced_block_with_ipv4_and_ipv6(tmp_path, monkeypatch):
    blocker, hosts, calls = make_blocker(tmp_path, monkeypatch)
    blocker.apply(["reddit.com", "x.com"])
    text = hosts.read_text(encoding="utf-8")
    assert text.startswith(ORIGINAL)              # pre-existing lines intact
    assert START_MARK in text and END_MARK in text
    # Both address families are redirected — browsers try AAAA lookups too
    # (https://www.currentware.com/blog/how-to-block-websites-using-hosts-file/)
    assert "127.0.0.1 reddit.com" in text and "::1 reddit.com" in text
    assert "127.0.0.1 x.com" in text
    assert calls                                   # DNS cache flushed


def test_apply_is_idempotent_and_replaces_old_block(tmp_path, monkeypatch):
    blocker, hosts, _ = make_blocker(tmp_path, monkeypatch)
    blocker.apply(["reddit.com", "youtube.com"])
    blocker.apply(["reddit.com"])                  # re-apply with smaller list
    text = hosts.read_text(encoding="utf-8")
    assert text.count(START_MARK) == 1             # exactly one fenced block
    assert "youtube.com" not in text               # old entries fully replaced


def test_clear_restores_original_content(tmp_path, monkeypatch):
    blocker, hosts, _ = make_blocker(tmp_path, monkeypatch)
    blocker.apply(["reddit.com"])
    blocker.clear()
    # Byte-for-byte restoration of the user's own hosts entries.
    assert hosts.read_text(encoding="utf-8") == ORIGINAL


def test_clear_without_block_is_safe(tmp_path, monkeypatch):
    blocker, hosts, _ = make_blocker(tmp_path, monkeypatch)
    blocker.clear()                                # nothing to remove → no-op
    assert hosts.read_text(encoding="utf-8") == ORIGINAL
