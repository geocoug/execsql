"""Attached SQLite targets retain their database qualifier during loads."""

import json

import pytest

from execsql import run
from execsql.db.sqlite import SQLiteDatabase


def _quote(name):
    return '"' + name.replace('"', '""') + '"'


_TARGET_NAMES = [("aux", "target"), ("aux space", "target space")]


@pytest.fixture
def target_db(request):
    schema, table = request.param
    db = SQLiteDatabase(":memory:")
    db.conn.execute(f"attach ':memory:' as {_quote(schema)}")
    main = f"main.{_quote(table)}"
    attached = f"{_quote(schema)}.{_quote(table)}"
    db.conn.execute(f"create table {main} (v text)")
    db.conn.execute(f"insert into {main} values ('main-before')")
    db.conn.execute("create table source (v text)")
    db.conn.execute("insert into source values ('source-row')")
    db.conn.commit()
    try:
        yield db, schema, table, main, attached
    finally:
        db.close()


@pytest.mark.parametrize("mode", ["", "NEW ", "REPLACEMENT "], ids=["existing", "new", "replacement"])
@pytest.mark.parametrize(
    ("target_db", "command"),
    [
        (names, command)
        for names in _TARGET_NAMES
        for command in ("csv", "json", "copy", "copy-query")
        # COPY's table-to-table grammar excludes spaces in target names.
        if command != "copy" or names == ("aux", "target")
    ],
    indirect=["target_db"],
)
def test_load_changes_only_the_qualified_target(target_db, tmp_path, mode, command):
    db, _schema, _table, main, attached = target_db
    if mode != "NEW ":
        db.conn.execute(f"create table {attached} (v text)")
        db.conn.execute(f"insert into {attached} values ('aux-before')")
        db.conn.commit()
    if command == "csv":
        source = tmp_path / "rows.csv"
        source.write_text("v\nsource-row\n", encoding="utf-8")
        statement = f'IMPORT TO {mode}{attached} FROM "{source}"'
    elif command == "json":
        source = tmp_path / "rows.json"
        source.write_text(json.dumps([{"v": "source-row"}]), encoding="utf-8")
        statement = f'IMPORT TO {mode}{attached} FROM JSON "{source}"'
    elif command == "copy":
        statement = f"COPY source FROM initial TO {mode}{attached} IN initial"
    else:
        statement = f"COPY QUERY <<select v from source;>> FROM initial TO {mode}{attached} IN initial"
    result = run(sql=f"-- !x! {statement}\n", connection=db)
    assert result.success, result.errors
    assert db.conn.execute(f"select v from {main}").fetchall() == [("main-before",)]
    expected = [("source-row",)] if mode else [("aux-before",), ("source-row",)]
    assert db.conn.execute(f"select v from {attached}").fetchall() == expected


@pytest.mark.parametrize("target_db", _TARGET_NAMES, indirect=True)
def test_column_lookup_uses_the_qualified_table(target_db):
    db, schema, table, _main, attached = target_db
    db.conn.execute(f"create table {attached} (attached_only text)")
    assert db.table_columns(table, schema) == ["attached_only"]
    assert db.column_exists(table, "attached_only", schema)
    assert not db.column_exists(table, "v", schema)


@pytest.mark.parametrize("target_db", _TARGET_NAMES, indirect=True)
def test_table_lookup_does_not_fall_back_to_main(target_db):
    db, schema, table, _main, attached = target_db
    assert not db.table_exists(table, schema)
    db.conn.execute(f"create table {attached} (v text)")
    assert db.table_exists(table, schema)
    db.conn.execute(f"create table {_quote(schema)}.only_attached (v text)")
    assert db.table_exists("only_attached", schema)
    assert not db.table_exists("only_attached")


@pytest.mark.parametrize("target_db", _TARGET_NAMES, indirect=True)
@pytest.mark.parametrize("schema", ["aux", "not_attached"])
def test_missing_qualified_target_cannot_load_into_main(target_db, tmp_path, schema):
    db, _schema, table, main, _attached = target_db
    source = tmp_path / "rows.csv"
    source.write_text("v\nsource-row\n", encoding="utf-8")
    statement = f'IMPORT TO {_quote(schema)}.{_quote(table)} FROM "{source}"'
    result = run(sql=f"-- !x! {statement}\n", connection=db)
    assert not result.success
    assert db.conn.execute(f"select v from {main}").fetchall() == [("main-before",)]


def test_qualifiers_with_quotes_are_quoted_as_identifiers():
    db = SQLiteDatabase(":memory:")
    schema, table = 'aux"name', 'target"name'
    try:
        db.conn.execute(f"attach ':memory:' as {_quote(schema)}")
        db.conn.execute(f"create table {_quote(schema)}.{_quote(table)} (v text)")
        assert db.table_exists(table, schema)
        assert db.table_columns(table, schema) == ["v"]
    finally:
        db.close()
