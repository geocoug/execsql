"""
Tests for exporter functions that take a db argument.

These exporters call ``db.select_rowsource(sql)`` to obtain headers and rows.
A lightweight FakeDB class is used instead of a real connection.

Functions covered:
  - exporters.json.write_query_to_json
  - exporters.json.write_query_to_json_ts
  - exporters.xml.write_query_to_xml
"""

from __future__ import annotations

import json as _json

import pytest

from execsql.exceptions import ErrInfo
from execsql.exporters.json import write_query_to_json, write_query_to_json_ts
from execsql.exporters.xml import write_query_to_xml


# ---------------------------------------------------------------------------
# Fake DB
# ---------------------------------------------------------------------------


class FakeDB:
    """Minimal DB stub that returns fixed headers and rows from select_rowsource."""

    def __init__(self, hdrs, rows):
        self._hdrs = hdrs
        self._rows = iter(rows)

    def select_rowsource(self, sql):
        return self._hdrs, self._rows


class ErrorDB:
    """DB stub that raises a generic Exception (non-ErrInfo) on select."""

    def select_rowsource(self, sql):
        raise RuntimeError("driver error")


# ---------------------------------------------------------------------------
# write_query_to_json
# ---------------------------------------------------------------------------


class TestWriteQueryToJson:
    def test_writes_json_array(self, noop_filewriter_close, tmp_path):
        db = FakeDB(["id", "name"], [(1, "Alice"), (2, "Bob")])
        out = str(tmp_path / "out.json")
        write_query_to_json("SELECT * FROM t", db, out)
        data = _json.loads((tmp_path / "out.json").read_text())
        assert isinstance(data, list)
        assert len(data) == 2

    def test_json_contains_expected_keys(self, noop_filewriter_close, tmp_path):
        db = FakeDB(["id", "name"], [(1, "Alice")])
        out = str(tmp_path / "out.json")
        write_query_to_json("SELECT * FROM t", db, out)
        data = _json.loads((tmp_path / "out.json").read_text())
        assert "id" in data[0]
        assert "name" in data[0]

    def test_json_empty_resultset(self, noop_filewriter_close, tmp_path):
        db = FakeDB(["id"], [])
        out = str(tmp_path / "out.json")
        write_query_to_json("SELECT * FROM t", db, out)
        data = _json.loads((tmp_path / "out.json").read_text())
        assert data == []

    def test_driver_error_raises_errinfo(self, noop_filewriter_close, tmp_path):
        db = ErrorDB()
        with pytest.raises(ErrInfo):
            write_query_to_json("SELECT 1", db, str(tmp_path / "out.json"))

    def test_append_mode(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.json")
        db1 = FakeDB(["x"], [(1,)])
        write_query_to_json("SELECT x FROM t", db1, out)
        size_first = (tmp_path / "out.json").stat().st_size
        db2 = FakeDB(["x"], [(2,)])
        write_query_to_json("SELECT x FROM t", db2, out, append=True)
        assert (tmp_path / "out.json").stat().st_size > size_first

    def test_none_value_serialized(self, noop_filewriter_close, tmp_path):
        db = FakeDB(["id", "val"], [(1, None)])
        out = str(tmp_path / "out.json")
        write_query_to_json("SELECT * FROM t", db, out)
        text = (tmp_path / "out.json").read_text()
        assert "null" in text


# ---------------------------------------------------------------------------
# write_query_to_json_ts (JSON with type schema header)
# ---------------------------------------------------------------------------


class TestWriteQueryToJsonTs:
    def test_writes_json_object_with_fields(self, noop_filewriter_close, tmp_path):
        db = FakeDB(["id", "name"], [(1, "Alice"), (2, "Bob")])
        out = str(tmp_path / "out.json")
        write_query_to_json_ts("SELECT * FROM t", db, out, write_types=False)
        text = (tmp_path / "out.json").read_text()
        assert '"fields"' in text

    def test_writes_description(self, noop_filewriter_close, tmp_path):
        db = FakeDB(["id"], [(1,)])
        out = str(tmp_path / "out.json")
        write_query_to_json_ts("SELECT * FROM t", db, out, desc="My dataset", write_types=False)
        text = (tmp_path / "out.json").read_text()
        assert "My dataset" in text

    def test_no_write_types(self, noop_filewriter_close, tmp_path):
        db = FakeDB(["id", "name"], [(1, "Alice")])
        out = str(tmp_path / "out.json")
        write_query_to_json_ts("SELECT * FROM t", db, out, write_types=False)
        text = (tmp_path / "out.json").read_text()
        assert '"name"' in text

    def test_driver_error_raises_errinfo(self, noop_filewriter_close, tmp_path):
        db = ErrorDB()
        with pytest.raises(ErrInfo):
            write_query_to_json_ts("SELECT 1", db, str(tmp_path / "out.json"))


# ---------------------------------------------------------------------------
# write_query_to_xml
# ---------------------------------------------------------------------------


class TestWriteQueryToXml:
    def test_writes_xml_root_element(self, noop_filewriter_close, tmp_path):
        db = FakeDB(["id", "name"], [(1, "Alice"), (2, "Bob")])
        out = str(tmp_path / "out.xml")
        write_query_to_xml("SELECT * FROM t", "records", db, out)
        text = (tmp_path / "out.xml").read_text()
        assert "<records>" in text
        assert "</records>" in text

    def test_writes_row_elements(self, noop_filewriter_close, tmp_path):
        db = FakeDB(["id"], [(42,)])
        out = str(tmp_path / "out.xml")
        write_query_to_xml("SELECT * FROM t", "data", db, out)
        text = (tmp_path / "out.xml").read_text()
        assert "<row>" in text
        assert "<id>42</id>" in text

    def test_writes_xml_declaration(self, noop_filewriter_close, tmp_path):
        db = FakeDB(["id"], [(1,)])
        out = str(tmp_path / "out.xml")
        write_query_to_xml("SELECT * FROM t", "root", db, out)
        text = (tmp_path / "out.xml").read_text()
        assert "<?xml" in text

    def test_writes_description_comment(self, noop_filewriter_close, tmp_path):
        db = FakeDB(["id"], [(1,)])
        out = str(tmp_path / "out.xml")
        write_query_to_xml("SELECT * FROM t", "root", db, out, desc="My data")
        text = (tmp_path / "out.xml").read_text()
        assert "<!--My data-->" in text

    def test_driver_error_raises_errinfo(self, noop_filewriter_close, tmp_path):
        db = ErrorDB()
        with pytest.raises(ErrInfo):
            write_query_to_xml("SELECT 1", "root", db, str(tmp_path / "out.xml"))

    def test_empty_resultset(self, noop_filewriter_close, tmp_path):
        db = FakeDB(["id"], [])
        out = str(tmp_path / "out.xml")
        write_query_to_xml("SELECT * FROM t", "root", db, out)
        text = (tmp_path / "out.xml").read_text()
        assert "<root>" in text
        assert "</root>" in text
        assert "<row>" not in text
