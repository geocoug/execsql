"""Repeated and interrupted ``execsql.run()`` calls in one long-lived process.

Embedding hosts (notebooks, schedulers, services) call ``run()`` many times.
Nothing a run creates may accumulate across calls, and an interrupted run must
not leave its connection open.
"""

from __future__ import annotations

import atexit
from unittest.mock import MagicMock

import pytest

from execsql import api


def _dsn(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'iso.db'}"


def test_repeated_runs_do_not_accumulate_exit_hooks_or_commands(tmp_path):
    from execsql.metacommands import DISPATCH_TABLE

    api.run(sql="select 1;", dsn=_dsn(tmp_path), new_db=True)  # warm-up
    hooks = atexit._ncallbacks()
    commands = len(DISPATCH_TABLE._commands)
    for _ in range(10):
        result = api.run(sql="select 1;", dsn=_dsn(tmp_path), new_db=True)
        assert result.success, result.errors
    assert atexit._ncallbacks() == hooks
    assert len(DISPATCH_TABLE._commands) == commands


def test_plugins_register_once_per_dispatch_table(monkeypatch):
    from execsql import plugins
    from execsql.script.engine import MetaCommandList

    calls = []
    monkeypatch.setattr(plugins, "_load_entry_points", lambda group: [("p", calls.append)])
    table = MetaCommandList()
    assert plugins.register_metacommand_plugins_once(table) == 1
    assert plugins.register_metacommand_plugins_once(table) == 0
    assert calls == [table]


def test_interrupted_run_closes_the_owned_connection(tmp_path, monkeypatch):
    import execsql.script.executor as executor

    opened = {}
    real_connect = api._connect_from_dsn

    def connect_and_spy(*args, **kwargs):
        db = real_connect(*args, **kwargs)
        db.close = MagicMock(side_effect=db.close)
        opened["db"] = db
        return db

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(api, "_connect_from_dsn", connect_and_spy)
    monkeypatch.setattr(executor, "execute", interrupt)
    with pytest.raises(KeyboardInterrupt):
        api.run(sql="select 1;", dsn=_dsn(tmp_path), new_db=True)
    assert opened["db"].close.called


def test_run_does_not_record_into_the_callers_manifest(tmp_path):
    """A CLI-style manifest active in this thread belongs to that run only."""
    from execsql import manifest as _manifest

    rec = _manifest.start(str(tmp_path / "m.json"), "outer.sql", [])
    try:
        api.run(sql="select 1;\nselect 2;\n", dsn=_dsn(tmp_path), new_db=True)
        assert rec.sql_statements == 0
        assert _manifest.current() is rec
    finally:
        rec.finish(0)


def test_temp_file_manager_drops_its_exit_hook():
    from execsql.utils.fileio import TempFileMgr

    before = atexit._ncallbacks()
    mgr = TempFileMgr()
    fn = mgr.new_temp_fn()
    mgr.remove_all()
    assert atexit._ncallbacks() == before
    import os

    assert not os.path.exists(fn)
