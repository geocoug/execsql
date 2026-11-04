"""Catalog failures must reach the executor before a partial batch can commit (#136)."""

from __future__ import annotations

import sqlite3
from unittest.mock import Mock

import pytest

from execsql import run
from execsql.db.sqlite import SQLiteDatabase
from execsql.exceptions import ErrInfo


_COMMANDS = [
    pytest.param("IMPORT TO NEW lookup FROM {d}/input.csv", False, id="csv"),
    pytest.param("IMPORT TO NEW lookup FROM JSON {d}/input.json", False, id="json"),
    pytest.param("COPY source FROM initial TO NEW lookup IN initial", False, id="copy"),
    pytest.param("IMPORT TO NEW lookup FROM {d}/input.csv", True, id="current-schema"),
    pytest.param("WRITE CREATE_TABLE lookup FROM output IN initial", False, id="write"),
    pytest.param('PROMPT ENTRY_FORM lookup MESSAGE "Enter values"', False, id="entry-form"),
    pytest.param('PROMPT ACTION lookup MESSAGE "Choose"', False, id="action"),
]


@pytest.mark.parametrize(("command", "schema_failure"), _COMMANDS)
@pytest.mark.parametrize("mode", ["continue", "nested", "metacommand-halt", "sql-halt", "autocommit-off"])
def test_catalog_failure_is_reported_and_cannot_commit_a_partial_batch(
    tmp_path,
    monkeypatch,
    command,
    schema_failure,
    mode,
):
    (tmp_path / "input.csv").write_text("v\nloaded\n", encoding="utf-8")
    (tmp_path / "input.json").write_text('[{"v": "loaded"}]', encoding="utf-8")
    db = SQLiteDatabase(str(tmp_path / "t.db"))
    db.conn.executescript("create table t (v text); create table source (v text);")
    if command.startswith(("WRITE", "PROMPT")):
        db.conn.execute("create table lookup (v text)")
    lookup = Mock()
    original = SQLiteDatabase.table_exists

    def fail(self):
        lookup()
        self.rollback()  # What an adapter does after a failed catalog query.
        raise ErrInfo(type="db", other_msg="Catalog lookup failed")

    def table_exists(self, table, schema=None):
        if table == "lookup" and not lookup.called:
            fail(self)
        return original(self, table, schema)

    if schema_failure:
        monkeypatch.setattr(SQLiteDatabase, "unqualified_lookup_is_scoped", False)
        monkeypatch.setattr(SQLiteDatabase, "current_schema", fail)
    else:
        monkeypatch.setattr(SQLiteDatabase, "table_exists", table_exists)
    gui = Mock(side_effect=AssertionError("A failed lookup must not open a dialog"))
    monkeypatch.setattr("execsql.metacommands.prompt.enable_gui", gui)
    script = (
        f"-- !x! ERROR_HALT {'ON' if mode == 'sql-halt' else 'OFF'}\n"
        f"-- !x! METACOMMAND_ERROR_HALT {'ON' if mode == 'metacommand-halt' else 'OFF'}\n"
        + ("-- !x! AUTOCOMMIT OFF\n" if mode == "autocommit-off" else "")
        + "-- !x! BEGIN BATCH\ninsert into t values ('A');\n"
        + ("-- !x! BEGIN BATCH\n" if mode == "nested" else "")
        + f"-- !x! {command.format(d=tmp_path)}\n"
        + "-- !x! IF (METACOMMAND_ERROR()) { SUB lookup_failed yes }\n"
        + "insert into t values ('B');\n-- !x! END BATCH\n"
        + "-- !x! IF (SQL_ERROR()) { SUB batch_failed yes }\n"
        + ("-- !x! END BATCH\n-- !x! IF (SQL_ERROR()) { SUB outer_failed yes }\n" if mode == "nested" else "")
        + "-- !x! SUB reached_end yes\n"
    )
    try:
        result = run(sql=script, connection=db)
        assert not result.success
        assert "Catalog lookup failed" in result.errors[0].message
        lookup.assert_called_once()
        gui.assert_not_called()
        if mode not in ("metacommand-halt", "sql-halt"):
            assert result.variables["lookup_failed"] == "yes"
            assert result.variables["batch_failed"] == "yes"
            assert result.variables["reached_end"] == "yes"
        else:
            assert "reached_end" not in result.variables
        if mode == "nested":
            assert result.variables["outer_failed"] == "yes"
        assert db.conn.execute("select v from t").fetchall() == ([("B",)] if mode == "autocommit-off" else [])
        with sqlite3.connect(tmp_path / "t.db") as observer:
            assert observer.execute("select v from t").fetchall() == []
    finally:
        db.conn.close()


@pytest.mark.parametrize(
    "command",
    [
        "WRITE CREATE_TABLE missing FROM output IN initial",
        'PROMPT ENTRY_FORM missing MESSAGE "Enter values"',
        'PROMPT ACTION missing MESSAGE "Choose"',
    ],
)
def test_missing_table_reports_the_check_error_before_reading_or_opening_a_dialog(tmp_path, monkeypatch, command):
    gui = Mock(side_effect=AssertionError("A missing table must not open a dialog"))
    monkeypatch.setattr("execsql.metacommands.prompt.enable_gui", gui)
    result = run(sql=f"-- !x! {command}\n", dsn=f"sqlite:///{tmp_path / 't.db'}", new_db=True)
    assert not result.success
    assert "Table missing does not exist" in result.errors[0].message
    assert result.errors[0].line == 1
    assert "no such table" not in result.errors[0].message
    gui.assert_not_called()


@pytest.mark.parametrize("command", [p.values[0] for p in _COMMANDS if not p.values[1]])
def test_real_sqlite_catalog_error_rolls_back_the_batch(tmp_path, command):
    """An unknown attached schema fails inside SQLite's actual catalog query."""
    (tmp_path / "input.csv").write_text("v\nloaded\n", encoding="utf-8")
    (tmp_path / "input.json").write_text('[{"v": "loaded"}]', encoding="utf-8")
    command = command.replace("lookup", "missing_schema.lookup").format(d=tmp_path)
    script = (
        "create table t (v text);\ncreate table source (v text);\n"
        "-- !x! ERROR_HALT OFF\n-- !x! METACOMMAND_ERROR_HALT OFF\n"
        "-- !x! BEGIN BATCH\ninsert into t values ('A');\n"
        f"-- !x! {command}\n"
        "-- !x! IF (METACOMMAND_ERROR()) { SUB lookup_failed yes }\n"
        "insert into t values ('B');\n-- !x! END BATCH\n"
        "-- !x! IF (SQL_ERROR()) { SUB batch_failed yes }\n"
    )
    result = run(sql=script, dsn=f"sqlite:///{tmp_path / 't.db'}", new_db=True)
    assert not result.success
    assert "missing_schema.sqlite_master" in result.errors[0].message
    assert result.variables["lookup_failed"] == "yes"
    assert result.variables["batch_failed"] == "yes"
    with sqlite3.connect(tmp_path / "t.db") as observer:
        assert observer.execute("select v from t").fetchall() == []
