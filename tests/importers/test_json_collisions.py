"""Ambiguous flattened JSON paths must fail before a load changes its target."""

import json

import pytest

from execsql import run
from execsql.db.sqlite import SQLiteDatabase
from execsql.exceptions import ErrInfo
from execsql.importers.json import _flatten

_COLLISIONS = [
    ({"a.b": 10, "a": {"b": 20}}, "a.b"),
    ({"a": {"b": 20}, "a.b": 10}, "a.b"),
    ({"a": {"b.c": 10, "b": {"c": 20}}}, "a.b.c"),
    ({"a": {"b": {"c": 20}, "b.c": 10}}, "a.b.c"),
    ({"a.b": {"c": 10}, "a": {"b.c": 20}}, "a.b.c"),
    ({"a.b": None, "a": {"b": []}}, "a.b"),
]


@pytest.mark.parametrize(("record", "column"), _COLLISIONS)
@pytest.mark.parametrize("file_format", ["array", "jsonl"])
@pytest.mark.parametrize("mode", ["", "NEW ", "REPLACEMENT "], ids=["existing", "new", "replacement"])
def test_collision_keeps_the_destination_unchanged(tmp_path, record, column, file_format, mode):
    db = SQLiteDatabase(":memory:")
    source = tmp_path / "records.json"
    records = [{column: "first-row"}, record]
    source.write_text(
        json.dumps(records) if file_format == "array" else "\n".join(json.dumps(row) for row in records),
        encoding="utf-8",
    )
    try:
        db.conn.execute("create table protected (v text)")
        db.conn.execute("insert into protected values ('keep')")
        if mode != "NEW ":
            db.conn.execute(f'create table target ("{column}" text)')
            db.conn.execute("insert into target values ('original')")
        db.conn.commit()
        result = run(sql=f'-- !x! IMPORT TO {mode}target FROM JSON "{source}"\n', connection=db)
        assert not result.success
        assert "same column" in result.errors[0].message
        assert column in result.errors[0].message
        assert db.conn.execute("select v from protected").fetchall() == [("keep",)]
        if mode == "NEW ":
            assert db.conn.execute("select name from sqlite_master where name='target'").fetchall() == []
        else:
            assert db.conn.execute("select * from target").fetchall() == [("original",)]
    finally:
        db.close()


def test_collision_message_identifies_both_source_paths():
    with pytest.raises(ErrInfo) as exc:
        _flatten({"a.b": 1, "a": {"b": 1}})
    assert '["a.b"]' in str(exc.value)
    assert '["a", "b"]' in str(exc.value)


def test_custom_separator_collisions_are_rejected():
    with pytest.raises(ErrInfo):
        _flatten({"a__b": 1, "a": {"b": 2}}, prefix="root", sep="__")


@pytest.mark.parametrize("file_format", ["array", "jsonl"])
def test_noncolliding_dotted_keys_and_values_are_preserved(tmp_path, file_format):
    db = SQLiteDatabase(":memory:")
    source = tmp_path / "records.json"
    tags = [1, {"x": "!!token!!"}]
    records = [{"a.b": "left", "a": {"c": "right"}, "tags": tags}, {"a.b": "later"}]
    source.write_text(
        json.dumps(records) if file_format == "array" else "\n".join(json.dumps(row) for row in records),
        encoding="utf-8",
    )
    try:
        result = run(sql=f'-- !x! IMPORT TO NEW target FROM JSON "{source}"\n', connection=db)
        assert result.success, result.errors
        assert db.conn.execute('select "a.b", "a.c", tags from target').fetchall() == [
            ("left", "right", json.dumps(tags)),
            ("later", None, None),
        ]
    finally:
        db.close()
