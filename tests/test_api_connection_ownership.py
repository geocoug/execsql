"""Run-created connections close deterministically without taking caller ownership."""

import sqlite3
from unittest.mock import MagicMock

import pytest

from execsql import run
from execsql import api
from execsql.db.base import DatabasePool
from execsql.db.sqlite import SQLiteDatabase


def _empty_secondary(path):
    conn = sqlite3.connect(path)
    try:
        conn.execute("create table pending (v integer)")
        conn.commit()
    finally:
        conn.close()


def _observe_created_connections(monkeypatch, exit_kind="success"):
    created = []

    class ObservedDatabase(SQLiteDatabase):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

        def execute(self, sql, *args, **kwargs):
            result = super().execute(sql, *args, **kwargs)
            if sql.strip().lower().startswith("insert into pending"):
                if exit_kind == "keyboard_interrupt":
                    raise KeyboardInterrupt
                if exit_kind == "system_exit":
                    raise SystemExit(143)
            return result

    monkeypatch.setattr("execsql.metacommands.connect.SQLiteDatabase", ObservedDatabase)
    return created


@pytest.mark.parametrize("caller_autocommit", [True, False], ids=["caller-autocommit-on", "caller-autocommit-off"])
@pytest.mark.parametrize("exit_kind", ["success", "sql_error", "halt", "keyboard_interrupt", "system_exit"])
def test_borrowing_initial_connection_does_not_leak_script_connections(
    tmp_path,
    monkeypatch,
    caller_autocommit,
    exit_kind,
):
    caller = SQLiteDatabase(str(tmp_path / "caller.db"))
    secondary = tmp_path / "secondary.db"
    _empty_secondary(secondary)
    created = _observe_created_connections(monkeypatch, exit_kind)
    caller.conn.execute("create table held (v integer)")
    caller.conn.commit()
    caller.conn.execute("insert into held values (1)")
    caller.autocommit = caller_autocommit
    script = (
        f'-- !x! CONNECT TO SQLITE(FILE="{secondary}") AS extra\n'
        "-- !x! USE extra\n-- !x! AUTOCOMMIT OFF\ninsert into pending values (1);\n"
    )
    if exit_kind == "sql_error":
        script += "select * from missing_table;\n"
    elif exit_kind == "halt":
        script += "-- !x! HALT\n"
    try:
        if exit_kind == "keyboard_interrupt":
            with pytest.raises(KeyboardInterrupt):
                run(sql=script, connection=caller)
        else:
            result = run(sql=script, connection=caller)
            assert result.success == (exit_kind == "success"), result.errors
        assert len(created) == 1
        assert created[0].conn is None
        assert caller.conn is not None
        interrupted = exit_kind in ("keyboard_interrupt", "system_exit")
        expected = [] if interrupted and caller_autocommit else [(1,)]
        assert caller.conn.execute("select * from held").fetchall() == expected
        # The caller's pending work is never committed by run's cleanup.
        observer = sqlite3.connect(tmp_path / "caller.db")
        try:
            assert observer.execute("select * from held").fetchall() == []
        finally:
            observer.close()
        observer = sqlite3.connect(secondary, timeout=0.05)
        try:
            assert observer.execute("select * from pending").fetchall() == []
            observer.execute("insert into pending values (2)")
            observer.commit()
        finally:
            observer.close()
    finally:
        for db in created:
            if db.conn is not None:
                db.rollback()
                db.close()
        caller.rollback()
        caller.close()


def test_owned_initial_and_script_connections_still_close(tmp_path, monkeypatch):
    secondary = tmp_path / "secondary.db"
    _empty_secondary(secondary)
    created = _observe_created_connections(monkeypatch)
    initial = []
    connect = api._connect_from_dsn

    def observe_initial(*args, **kwargs):
        db = connect(*args, **kwargs)
        initial.append(db)
        return db

    monkeypatch.setattr(api, "_connect_from_dsn", observe_initial)
    result = run(
        sql=(
            f'-- !x! CONNECT TO SQLITE(FILE="{secondary}") AS extra\n'
            "-- !x! USE extra\n-- !x! AUTOCOMMIT OFF\ninsert into pending values (1);\n"
        ),
        dsn=f"sqlite:///{tmp_path / 'initial.db'}",
        new_db=True,
    )
    assert result.success, result.errors
    assert len(initial) == len(created) == 1
    assert initial[0].conn is None
    assert created[0].conn is None


def test_pool_excludes_the_borrowed_object_under_every_alias(monkeypatch):
    borrowed, owned = SQLiteDatabase(":memory:"), SQLiteDatabase(":memory:")
    borrowed.conn.execute("create table held (v integer)")
    borrowed.conn.execute("insert into held values (1)")
    rollback = MagicMock(wraps=borrowed.rollback)
    close = MagicMock(wraps=borrowed.close)
    monkeypatch.setattr(borrowed, "rollback", rollback)
    monkeypatch.setattr(borrowed, "close", close)
    pool = DatabasePool()
    pool.add("initial", borrowed)
    pool.add("borrowed_again", borrowed)
    pool.add("owned", owned)
    try:
        pool.closeall(except_db=borrowed)
        rollback.assert_not_called()
        close.assert_not_called()
        assert borrowed.conn.execute("select * from held").fetchall() == [(1,)]
        assert owned.conn is None
        assert pool.aliases() == []
        assert pool.initial_db is pool.current_db is None
    finally:
        borrowed.rollback()
        borrowed.close()
        if owned.conn is not None:
            owned.close()
