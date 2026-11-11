"""Catalog failures must reach the executor before a partial batch can commit (#136)."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
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
]

_READ_COMMANDS = [
    "WRITE CREATE_TABLE lookup FROM output IN initial",
    'PROMPT ENTRY_FORM lookup MESSAGE "Enter values"',
    'PROMPT ACTION lookup MESSAGE "Choose"',
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
def test_missing_table_reports_the_read_error_without_opening_a_dialog(tmp_path, monkeypatch, command):
    gui = Mock(side_effect=AssertionError("A missing table must not open a dialog"))
    monkeypatch.setattr("execsql.metacommands.prompt.enable_gui", gui)
    result = run(sql=f"-- !x! {command}\n", dsn=f"sqlite:///{tmp_path / 't.db'}", new_db=True)
    assert not result.success
    assert "no such table: missing" in result.errors[0].message
    assert result.errors[0].line == 1
    gui.assert_not_called()


@pytest.mark.parametrize("command", [p.values[0] for p in _COMMANDS if not p.values[1]] + _READ_COMMANDS)
def test_real_sqlite_catalog_or_source_error_rolls_back_the_batch(tmp_path, command):
    """An unknown attached schema fails inside SQLite's actual catalog query or SELECT."""
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
    assert "missing_schema." in result.errors[0].message
    assert result.variables["lookup_failed"] == "yes"
    assert result.variables["batch_failed"] == "yes"
    with sqlite3.connect(tmp_path / "t.db") as observer:
        assert observer.execute("select v from t").fetchall() == []


@pytest.mark.parametrize("source_kind", ["temp table", "view"])
@pytest.mark.parametrize(
    ("command", "query"),
    [
        (_READ_COMMANDS[0], "select 1 as v"),
        (_READ_COMMANDS[1], "select 'answer' as sub_var, 'Value' as prompt"),
        (_READ_COMMANDS[2], "select 'Run' as label, 'Run script' as prompt, 'noop' as script"),
    ],
)
def test_readable_sources_need_no_catalog_access(tmp_path, monkeypatch, source_kind, command, query):
    import execsql.state as state

    catalog = Mock(side_effect=AssertionError("Read-only sources need no catalog query"))
    monkeypatch.setattr(SQLiteDatabase, "table_exists", catalog)
    dialogs = []

    def respond(spec):
        dialogs.append(spec)
        response = {"button": 1, "row": None} if spec.gui_type == "action" else {"button": 1, "return_value": []}
        spec.return_queue.put(response)

    def enable_gui():
        state.gui_manager_queue = SimpleNamespace(put=respond)

    monkeypatch.setattr("execsql.metacommands.prompt.enable_gui", enable_gui)
    script = f"create {source_kind} lookup as {query};\n-- !x! {command}\n"
    if command.startswith("PROMPT ACTION"):
        script += "-- !x! BEGIN SCRIPT noop\n-- !x! SUB action_ran yes\n-- !x! END SCRIPT\n"
    result = run(sql=script, dsn=f"sqlite:///{tmp_path / 't.db'}", new_db=True)
    assert result.success, result.errors
    if command.startswith("PROMPT ACTION"):
        assert result.variables["action_ran"] == "yes"
    catalog.assert_not_called()
    assert len(dialogs) == (1 if command.startswith("PROMPT") else 0)
