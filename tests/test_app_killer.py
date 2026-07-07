# Tests for deepwork/blocking/app_killer.py — psutil is monkeypatched with
# fake process objects so no real program is ever killed by the test suite.
# psutil API being faked: https://psutil.readthedocs.io/en/latest/#psutil.process_iter

import psutil
import pytest

from deepwork.blocking import app_killer


class FakeProc:
    # Mimics the two psutil.Process members app_killer uses: .info["name"]
    # (pre-fetched by process_iter(["name"])) and .kill().
    def __init__(self, name, raises=None):
        self.info = {"name": name, "pid": 1234}
        self.killed = False
        self._raises = raises

    def kill(self):
        if self._raises:
            raise self._raises
        self.killed = True


def patch_procs(monkeypatch, procs):
    # process_iter is a module-level generator function in psutil.
    monkeypatch.setattr(psutil, "process_iter", lambda attrs=None: iter(procs))


def test_kills_only_targets_case_insensitively(monkeypatch):
    target = FakeProc("Discord.exe")               # Windows names vary in case
    bystander = FakeProc("code.exe")
    patch_procs(monkeypatch, [target, bystander])
    killed = app_killer.kill_targets(["discord.exe"])
    assert killed == ["Discord.exe"]
    assert target.killed and not bystander.killed


def test_survives_process_races_and_permissions(monkeypatch):
    # A process may exit between iteration and kill (NoSuchProcess) or be
    # protected (AccessDenied) — both documented psutil exceptions:
    # https://psutil.readthedocs.io/en/latest/#psutil.NoSuchProcess
    vanishing = FakeProc("steam.exe", raises=psutil.NoSuchProcess(1234))
    protected = FakeProc("telegram.exe", raises=psutil.AccessDenied(1234))
    patch_procs(monkeypatch, [vanishing, protected])
    # Must not raise; neither counts as killed.
    assert app_killer.kill_targets(["steam.exe", "telegram.exe"]) == []


def test_empty_target_list_kills_nothing(monkeypatch):
    proc = FakeProc("discord.exe")
    patch_procs(monkeypatch, [proc])
    assert app_killer.kill_targets([]) == []
    assert not proc.killed
