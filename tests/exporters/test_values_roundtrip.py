"""EXPORT … AS VALUES writes a file execsql runs back into the same rows.

The file is meant to be run with INCLUDE (``INSERT INTO !!target_table!!``), and
execsql reads it line by line: it substitutes variables, runs ``-- !x!``
lines as metacommands and ends a statement at a line ending in ``;``, inside
string literals too.  Values carrying any of those must still arrive
unchanged, and no metacommand may run from data.
"""

from __future__ import annotations

import sqlite3

import pytest

from execsql import run

NASTY = [
    (1, "plain", "O'Brien"),
    (2, "subst", "bang !!$DATE_TAG!! here"),
    (3, "metacommand", 'line one\n-- !x! write "INJECTED"\nline three'),
    (4, "semicolon", "ends with semi;\nnext line"),
    (5, "other markers", "!'!x!'! and !\"!y!\"! and !{z}! and !!"),
    (6, "windows newline", "a\r\nb\rc"),
    (7, None, None),
]


def _script(create: str) -> str:
    return (
        f"{create}\n"
        "-- !x! EXPORT src TO v.sql AS VALUES\n"
        'create table dst (id integer, "order" varchar(40), note varchar(200));\n'
        "-- !x! SUB target_table dst\n"
        "-- !x! INCLUDE v.sql\n"
    )


def test_sqlite_round_trip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = tmp_path / "t.db"
    con = sqlite3.connect(db)
    con.execute('create table src (id integer, "order" varchar(40), note varchar(200))')
    con.executemany("insert into src values (?, ?, ?)", NASTY)
    con.commit()
    con.close()
    result = run(sql=_script(""), dsn=f"sqlite:///{db}")
    assert result.success, result.errors
    con = sqlite3.connect(db)
    assert con.execute('select id, "order", note from dst order by id').fetchall() == NASTY


def test_duckdb_round_trip(tmp_path, monkeypatch):
    duckdb = pytest.importorskip("duckdb")
    monkeypatch.chdir(tmp_path)
    db = tmp_path / "t.duckdb"
    con = duckdb.connect(str(db))
    con.execute('create table src (id integer, "order" varchar, note varchar)')
    con.executemany("insert into src values (?, ?, ?)", NASTY)
    con.close()
    result = run(sql=_script(""), dsn=f"duckdb:///{db}")
    assert result.success, result.errors
    con = duckdb.connect(str(db))
    assert con.execute('select id, "order", note from dst order by id').fetchall() == NASTY


def test_no_metacommand_runs_from_data(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    db = tmp_path / "t.db"
    con = sqlite3.connect(db)
    con.execute('create table src (id integer, "order" varchar(40), note varchar(200))')
    con.executemany("insert into src values (?, ?, ?)", NASTY[2:3])
    con.commit()
    con.close()
    from execsql.cli import app
    from typer.testing import CliRunner

    (tmp_path / "s.sql").write_text(_script(""))
    out = CliRunner().invoke(app, ["run", "s.sql", str(db), "-t", "l"]).output
    assert "INJECTED" not in out


def test_an_empty_result_writes_a_file_that_runs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = tmp_path / "t.db"
    result = run(
        sql=_script('create table src (id integer, "order" varchar(40), note varchar(200));'),
        dsn=f"sqlite:///{db}",
        new_db=True,
    )
    assert result.success, result.errors
    assert "no rows" in (tmp_path / "v.sql").read_text()


@pytest.mark.parametrize(
    ("dbms", "expected"),
    [
        (None, "('a' || CHR(10) || 'b')"),
        ("SQLite", "('a' || char(10) || 'b')"),
        ("MySQL", "CONCAT('a', CHAR(10 USING utf8mb4), 'b')"),
        ("SQL Server", "('a' + CHAR(10) + 'b')"),
        ("Access", "('a' & Chr(10) & 'b')"),
        ("Firebird", "('a' || ASCII_CHAR(10) || 'b')"),
    ],
)
def test_a_line_break_is_written_in_each_dbms_syntax(dbms, expected):
    from execsql.exporters.values import _sql_literal

    assert _sql_literal("a\nb", dbms) == expected


def test_a_plain_value_is_one_literal():
    from execsql.exporters.values import _sql_literal

    assert _sql_literal("it's fine; really!", None) == "'it''s fine; really!'"
