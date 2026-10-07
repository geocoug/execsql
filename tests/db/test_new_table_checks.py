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
