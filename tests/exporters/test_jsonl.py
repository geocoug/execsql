"""EXPORT … AS JSONL: JSON Lines, one object per row (issue #7)."""

from __future__ import annotations

import json
import zipfile
from unittest.mock import MagicMock

import pytest

from execsql import run
from execsql.exceptions import ErrInfo
from execsql.exporters.json import write_query_to_json, write_query_to_jsonl

from .conftest import TABLE_NAME


@pytest.fixture
def zip_conf(minimal_conf):
    minimal_conf.zip_buffer_mb = 1
    return minimal_conf


def _make_db(headers, rows):
    db = MagicMock()
    db.select_rowsource.return_value = (headers, rows)
    return db


def _lines(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f.read().splitlines()]


class TestWriteQueryToJsonl:
    def test_one_object_per_line(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "o.jsonl"
        write_query_to_jsonl("select 1", _make_db(["id", "name"], [[1, "a"], [2, None]]), str(out))
        assert out.read_text(encoding="utf-8") == '{"id":1,"name":"a"}\n{"id":2,"name":null}\n'

    def test_a_line_break_in_a_value_stays_on_its_line(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "o.jsonl"
        write_query_to_jsonl("select 1", _make_db(["t"], [["one\ntwo\r\nthree"], ["x"]]), str(out))
        assert _lines(out) == [{"t": "one\ntwo\r\nthree"}, {"t": "x"}]

    def test_append_adds_lines_and_stays_valid(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "o.jsonl"
        write_query_to_jsonl("select 1", _make_db(["id"], [[1]]), str(out))
        write_query_to_jsonl("select 1", _make_db(["id"], [[2], [3]]), str(out), append=True)
        assert _lines(out) == [{"id": 1}, {"id": 2}, {"id": 3}]

    def test_without_append_the_file_is_replaced(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "o.jsonl"
        write_query_to_jsonl("select 1", _make_db(["id"], [[1]]), str(out))
        write_query_to_jsonl("select 1", _make_db(["id"], [[2]]), str(out))
        assert _lines(out) == [{"id": 2}]

    def test_no_rows_writes_an_empty_file(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "o.jsonl"
        write_query_to_jsonl("select 1", _make_db(["id"], []), str(out))
        assert out.read_text(encoding="utf-8") == ""

    def test_into_a_zipfile(self, noop_filewriter_close, zip_conf, tmp_path):
        zpath = str(tmp_path / "o.zip")
        write_query_to_jsonl("select 1", _make_db(["id"], [[1], [2]]), "o.jsonl", zipfile=zpath)
        with zipfile.ZipFile(zpath) as zf:
            assert zf.read("o.jsonl").decode("utf-8") == '{"id":1}\n{"id":2}\n'

    def test_db_error_raises(self, noop_filewriter_close, tmp_path):
        db = MagicMock()
        db.select_rowsource.side_effect = RuntimeError("boom")
        with pytest.raises(ErrInfo):
            write_query_to_jsonl("select 1", db, str(tmp_path / "o.jsonl"))


def test_each_line_holds_the_values_json_writes_for_that_row(export_db, tmp_path):
    """Every column type of the round-trip table comes out of JSONL exactly as out of JSON."""
    sql = f"select * from {TABLE_NAME} order by id;"
    write_query_to_json(sql, export_db, str(tmp_path / "o.json"))
    write_query_to_jsonl(sql, export_db, str(tmp_path / "o.jsonl"))
    with open(tmp_path / "o.json", encoding="utf-8") as f:
        expected = json.load(f)
    assert _lines(tmp_path / "o.jsonl") == expected


def test_export_as_jsonl_reads_back_with_import_from_json(tmp_path):
    out = tmp_path / "o.jsonl"
    result = run(
        sql=(
            "create table t (id integer, name text);\n"
            "insert into t values (1, 'a'), (2, null);\n"
            f"-- !x! EXPORT t TO {out} AS JSONL\n"
            f"-- !x! EXPORT QUERY <<select 3 as id, 'c' as name;>> APPEND TO {out} AS jsonl\n"
            f"-- !x! IMPORT TO NEW back FROM JSON {out}\n"
            f"-- !x! EXPORT QUERY <<select id, name from back order by id;>> TO {tmp_path / 'back.csv'} AS CSV\n"
        ),
        dsn=f"sqlite:///{tmp_path / 'x.db'}",
        new_db=True,
    )
    assert result.success, result.errors
    assert (tmp_path / "back.csv").read_text().splitlines() == ["id,name", "1,a", "2,", "3,c"]
