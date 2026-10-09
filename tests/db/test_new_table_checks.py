"""``TO NEW`` refuses an existing table with execsql's own message, before any DDL.

The checks are best effort: when the database cannot say whether the table
exists, the command goes ahead and the database reports any problem itself.
"""

from __future__ import annotations

import json

import pytest

from execsql import run


def _run(tmp_path, script):
    return run(sql=script, dsn=f"sqlite:///{tmp_path / 't.db'}", new_db=True)


def _message(result):
    assert not result.success
    return result.errors[0].message


@pytest.fixture
def files(tmp_path):
    (tmp_path / "q.csv").write_text("a,b\n1,2\n")
    (tmp_path / "q.json").write_text(json.dumps([{"a": 1, "b": 2}]))
    return tmp_path


@pytest.mark.parametrize(
    "command",
    [
        "IMPORT TO NEW lab FROM {d}/q.csv",
        "IMPORT TO NEW lab FROM JSON {d}/q.json",
        "COPY src_t FROM initial TO NEW lab IN initial",
        "COPY QUERY <<select * from src_t;>> FROM initial TO NEW lab IN initial",
    ],
    ids=["import-csv", "import-json", "copy", "copy-query"],
)
def test_new_onto_an_existing_table_is_refused_before_any_ddl(files, command):
    script = (
        "create table src_t (a integer, b integer);\n"
        "create table lab (keep text);\n"
        "insert into lab values ('original');\n"
        f"-- !x! {command.format(d=files)}\n"
    )
    message = _message(_run(files, script))
    assert "Table lab already exists" in message

    import sqlite3

    con = sqlite3.connect(files / "t.db")
    try:
        assert con.execute("select keep from lab").fetchall() == [("original",)]
    finally:
        con.close()


def test_copy_from_a_missing_source_reports_the_database_error(files):
    message = _message(_run(files, "-- !x! COPY no_such_table FROM initial TO NEW lab IN initial\n"))
    assert "no such table: no_such_table" in message


def test_a_check_the_database_cannot_answer_does_not_stop_the_command(files, monkeypatch):
    from execsql.db.sqlite import SQLiteDatabase

    original = SQLiteDatabase.table_exists
    calls = []

    def cannot_tell_the_first_time(self, *args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise RuntimeError("no catalog access")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(SQLiteDatabase, "table_exists", cannot_tell_the_first_time)
    result = _run(files, f"-- !x! IMPORT TO NEW lab FROM {files}/q.csv\n")
    assert result.success, result.errors


class TestOnlyTheTargetSchemaCounts:
    """An unqualified ``TO NEW t`` is refused only when ``t`` exists where CREATE TABLE would put it."""

    @staticmethod
    def _duckdb(tmp_path, script):
        pytest.importorskip("duckdb")
        return run(sql=script, dsn=f"duckdb:///{tmp_path / 'd.duckdb'}", new_db=True)

    @pytest.mark.parametrize(
        "command",
        ["IMPORT TO NEW two FROM {d}/q.csv", "COPY src_t FROM initial TO NEW two IN initial"],
        ids=["import", "copy"],
    )
    def test_a_same_named_table_in_another_schema_does_not_block(self, files, command):
        script = (
            "create table src_t (a integer, b integer);\n"
            "create schema other;\n"
            "create table other.two (z integer);\n"
            f"-- !x! {command.format(d=files)}\n"
        )
        result = self._duckdb(files, script)
        assert result.success, result.errors

    def test_the_same_table_in_the_target_schema_is_still_refused(self, files):
        script = "create schema other;\ncreate table other.two (z integer);\ncreate table two (z integer);\n"
        result = self._duckdb(files, script + f"-- !x! IMPORT TO NEW two FROM {files}/q.csv\n")
        assert "Table two already exists" in _message(result)


@pytest.mark.parametrize(
    ("module", "cls", "query", "schema"),
    [
        ("execsql.db.mysql", "MySQLDatabase", "select database()", "sales"),
        ("execsql.db.sqlserver", "SqlServerDatabase", "select schema_name()", "dbo"),
        ("execsql.db.oracle", "OracleDatabase", "select sys_context('USERENV', 'CURRENT_SCHEMA') from dual", "SCOTT"),
        ("execsql.db.duckdb", "DuckDBDatabase", "select current_schema()", "main"),
    ],
)
def test_server_adapters_look_where_create_table_would_put_the_table(module, cls, query, schema):
    """The unqualified lookup is narrowed to the session's current schema (or MySQL database)."""
    import importlib
    from contextlib import contextmanager
    from unittest.mock import MagicMock

    from execsql.importers.base import refuse_existing_table

    db = object.__new__(getattr(importlib.import_module(module), cls))
    curs = MagicMock()
    curs.fetchone.return_value = (schema,)

    @contextmanager
    def cursor():
        yield curs

    db._cursor = cursor  # type: ignore[method-assign]
    seen = []
    db.table_exists = lambda table, schema_name=None: seen.append((table, schema_name)) or False  # type: ignore[method-assign]
    refuse_existing_table(db, None, "two")
    curs.execute.assert_called_once_with(query)
    assert seen == [("two", schema)]


def test_a_dsn_that_cannot_name_its_schema_goes_ahead(monkeypatch):
    """Without a current schema an unqualified lookup would search every schema: cannot tell, so no refusal."""
    from execsql.db.dsn import DsnDatabase
    from execsql.importers.base import refuse_existing_table

    db = object.__new__(DsnDatabase)
    monkeypatch.setattr(DsnDatabase, "table_exists", lambda self, t, s=None: True)
    refuse_existing_table(db, None, "two")  # does not raise
