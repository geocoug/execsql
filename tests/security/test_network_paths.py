"""The static tools never touch a path written as a network path.

On Windows, checking whether ``\\\\host\\share\\x.sql`` exists makes the OS
contact *host* and offer the user's credentials, so a script or config file
from a cloned repository could make the language server, ``execsql lint`` or
``execsql format`` do that on open.  The Windows path rules are switched on
here, so the tests run on any OS; a recorder on ``os.stat`` and ``open``
fails the test if such a path is touched.
"""

from __future__ import annotations

import builtins
import os

import pytest

import execsql.utils.paths as paths
from execsql.utils.paths import is_network_path

EVIL_SQL = r"\\evil-host\share\setup.sql"
EVIL_INI = r"\\evil-host\share\vars.ini"
EVIL_CONF = r"\\evil-host\share\execsql.conf"


def _is_network(path) -> bool:
    text = os.fspath(path) if not isinstance(path, int) else ""
    return "evil-host" in text


@pytest.fixture
def windows_rules(monkeypatch):
    monkeypatch.setattr(paths, "_WINDOWS", True)


@pytest.fixture
def touched(monkeypatch):
    """Every network path os.stat or open was asked about."""
    seen: list[str] = []
    real_stat, real_open = os.stat, builtins.open

    def stat(path, *args, **kwargs):
        if _is_network(path):
            seen.append(os.fspath(path))
            raise FileNotFoundError(path)
        return real_stat(path, *args, **kwargs)

    def open_(file, *args, **kwargs):
        if _is_network(file):
            seen.append(os.fspath(file))
            raise FileNotFoundError(file)
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(os, "stat", stat)
    monkeypatch.setattr(builtins, "open", open_)
    return seen


@pytest.mark.parametrize(
    "path",
    [r"\\host\share\x.sql", "//host/share/x.sql", r"\/host/share", r"\\?\C:\x.sql", r"\\.\pipe\name"],
)
def test_unc_and_device_paths_are_network_paths_on_windows(windows_rules, path):
    assert is_network_path(path)


@pytest.mark.parametrize("path", [r"C:\data\x.sql", "data/x.sql", r"..\x.sql", "/srv/x.sql", "x.sql"])
def test_local_paths_are_not(windows_rules, path):
    assert not is_network_path(path)


def test_nothing_is_a_network_path_elsewhere(monkeypatch):
    monkeypatch.setattr(paths, "_WINDOWS", False)
    assert not is_network_path(r"\\host\share\x.sql")
    assert not is_network_path("//host/share/x.sql")


def test_the_language_server_index_does_not_follow_a_network_include(windows_rules, touched, tmp_path):
    pytest.importorskip("pygls")
    from execsql.lsp.document import index_script

    index = index_script(f"-- !x! INCLUDE {EVIL_SQL}\n-- !x! SUB here 1\n", str(tmp_path / "main.sql"))
    assert touched == []
    assert "HERE" in index.definitions
    assert index.includes == []


def test_lint_checks_neither_a_network_include_nor_ini(windows_rules, touched):
    from execsql.cli.lint import lint_source

    issues = lint_source(f"-- !x! INCLUDE {EVIL_SQL}\n-- !x! SUB_INI {EVIL_INI} SECTION s\n", "s.sql", "s.sql")
    assert touched == []
    assert not [i for i in issues if i.code == "I001"]


def _config_dir(tmp_path):
    (tmp_path / "execsql.conf").write_text(
        f"[config]\nconfig_file = {EVIL_CONF}\nwin_config_file = {EVIL_CONF}\n"
        f"[include_required]\n1 = {EVIL_SQL}\n[include_optional]\n1 = {EVIL_SQL}\n",
    )
    return str(tmp_path)


def test_the_static_tools_config_does_not_follow_a_network_chain(windows_rules, touched, tmp_path):
    from execsql.cli.run import _tool_config

    conf = _tool_config(None, start_dir=_config_dir(tmp_path))
    assert touched == []
    assert conf.include_req == [] and conf.include_opt == []


def test_a_run_still_follows_it(windows_rules, touched, tmp_path):
    """`execsql run` reads config the user chose, where a shared config on a server is a normal setup."""
    from execsql.cli.run import _load_config, _seed_early_subvars

    try:
        _load_config(None, _seed_early_subvars(), None, _config_dir(tmp_path))
    except Exception:  # the recorder's "not found" (or the missing required file) ends the load
        pass
    assert any("evil-host" in t for t in touched)
