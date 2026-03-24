"""
Tests for exporter functions that operate on already-fetched row data.

These functions write to files directly (not through the FileWriter subprocess),
so the ``noop_filewriter_close`` fixture from conftest is requested wherever
``_state.filewriter_close`` is called.

Functions covered:
  - exporters.values.export_values
  - exporters.raw.write_query_raw / write_query_b64
  - exporters.pretty.prettyprint_rowset
"""

from __future__ import annotations

import base64


from execsql.exporters.values import export_values
from execsql.exporters.raw import write_query_raw, write_query_b64
from execsql.exporters.pretty import prettyprint_rowset


# ---------------------------------------------------------------------------
# export_values
# ---------------------------------------------------------------------------


class TestExportValues:
    def test_writes_insert_statement(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.sql")
        export_values(out, ["id", "name"], [[1, "Alice"], [2, "Bob"]])
        text = (tmp_path / "out.sql").read_text()
        assert "INSERT INTO" in text
        assert "id" in text
        assert "name" in text

    def test_writes_values_rows(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.sql")
        export_values(out, ["id", "name"], [[1, "Alice"], [2, "Bob"]])
        text = (tmp_path / "out.sql").read_text()
        assert "'Alice'" in text
        assert "'Bob'" in text
        assert "1" in text
        assert "2" in text

    def test_null_values_written_as_null(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.sql")
        export_values(out, ["id", "val"], [[1, None]])
        text = (tmp_path / "out.sql").read_text()
        assert "NULL" in text

    def test_string_with_single_quote_escaped(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.sql")
        export_values(out, ["name"], [["O'Brien"]])
        text = (tmp_path / "out.sql").read_text()
        assert "O''Brien" in text

    def test_desc_written_as_comment(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.sql")
        export_values(out, ["id"], [[1]], desc="My description")
        text = (tmp_path / "out.sql").read_text()
        assert "-- My description" in text

    def test_no_desc_no_comment_line(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.sql")
        export_values(out, ["id"], [[1]])
        text = (tmp_path / "out.sql").read_text()
        assert not text.startswith("--")

    def test_append_mode_adds_comma(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.sql")
        export_values(out, ["id"], [[1]])
        size_first = (tmp_path / "out.sql").stat().st_size
        export_values(out, ["id"], [[2]], append=True)
        (tmp_path / "out.sql").read_text()
        # append=True opens in "at" mode so content accumulates
        assert size_first < (tmp_path / "out.sql").stat().st_size

    def test_empty_rows_writes_empty_values_block(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.sql")
        export_values(out, ["id"], [])
        text = (tmp_path / "out.sql").read_text()
        assert "INSERT INTO" in text
        assert "VALUES" in text

    def test_multiple_columns(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.sql")
        export_values(out, ["a", "b", "c"], [[1, 2.5, "hello"]])
        text = (tmp_path / "out.sql").read_text()
        assert "a, b, c" in text


# ---------------------------------------------------------------------------
# write_query_raw
# ---------------------------------------------------------------------------


class TestWriteQueryRaw:
    def test_writes_string_data(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "raw.bin")
        write_query_raw(out, [["hello"]], db_encoding="utf-8")
        assert (tmp_path / "raw.bin").read_bytes() == b"hello"

    def test_writes_bytes_data_as_str_repr(self, noop_filewriter_close, tmp_path):
        # bytes objects have no special case in write_query_raw; they fall through
        # to str(col) which produces the repr, e.g. b"hi" → "b'hi'".
        out = str(tmp_path / "raw.bin")
        write_query_raw(out, [[b"hi"]], db_encoding="utf-8")
        assert (tmp_path / "raw.bin").read_bytes() == bytes(str(b"hi"), "utf-8")

    def test_writes_bytearray_data(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "raw.bin")
        write_query_raw(out, [[bytearray(b"\x01\x02\x03")]], db_encoding="utf-8")
        assert (tmp_path / "raw.bin").read_bytes() == b"\x01\x02\x03"

    def test_writes_integer_as_string(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "raw.bin")
        write_query_raw(out, [[42]], db_encoding="utf-8")
        assert (tmp_path / "raw.bin").read_bytes() == b"42"

    def test_multiple_rows_and_cols(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "raw.bin")
        write_query_raw(out, [["ab", "cd"], ["ef"]], db_encoding="utf-8")
        assert (tmp_path / "raw.bin").read_bytes() == b"abcdef"

    def test_append_mode(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "raw.bin")
        write_query_raw(out, [["hello"]], db_encoding="utf-8")
        write_query_raw(out, [[" world"]], db_encoding="utf-8", append=True)
        assert (tmp_path / "raw.bin").read_bytes() == b"hello world"

    def test_empty_rowsource_creates_empty_file(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "raw.bin")
        write_query_raw(out, [], db_encoding="utf-8")
        assert (tmp_path / "raw.bin").read_bytes() == b""


# ---------------------------------------------------------------------------
# write_query_b64
# ---------------------------------------------------------------------------


class TestWriteQueryB64:
    def test_decodes_base64_to_file(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "decoded.bin")
        payload = base64.standard_b64encode(b"hello world")
        write_query_b64(out, [[payload]])
        assert (tmp_path / "decoded.bin").read_bytes() == b"hello world"

    def test_multiple_base64_chunks(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "decoded.bin")
        c1 = base64.standard_b64encode(b"foo")
        c2 = base64.standard_b64encode(b"bar")
        write_query_b64(out, [[c1, c2]])
        assert (tmp_path / "decoded.bin").read_bytes() == b"foobar"

    def test_append_mode(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "decoded.bin")
        c1 = base64.standard_b64encode(b"hello ")
        c2 = base64.standard_b64encode(b"world")
        write_query_b64(out, [[c1]])
        write_query_b64(out, [[c2]], append=True)
        assert (tmp_path / "decoded.bin").read_bytes() == b"hello world"


# ---------------------------------------------------------------------------
# prettyprint_rowset
# ---------------------------------------------------------------------------


class TestPrettyprintRowset:
    def test_writes_header_and_separator(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.txt")
        prettyprint_rowset(["id", "name"], [(1, "Alice"), (2, "Bob")], out)
        text = (tmp_path / "out.txt").read_text()
        assert "id" in text
        assert "name" in text
        # Separator line contains dashes
        assert "-" in text

    def test_writes_row_data(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.txt")
        prettyprint_rowset(["col"], [("value1",), ("value2",)], out)
        text = (tmp_path / "out.txt").read_text()
        assert "value1" in text
        assert "value2" in text

    def test_none_values_use_and_val(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.txt")
        prettyprint_rowset(["col"], [(None,)], out, and_val="N/A")
        text = (tmp_path / "out.txt").read_text()
        assert "N/A" in text

    def test_desc_written_at_top(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.txt")
        prettyprint_rowset(["col"], [("v",)], out, desc="My table")
        text = (tmp_path / "out.txt").read_text()
        assert text.startswith("My table\n")

    def test_no_desc_no_leading_line(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.txt")
        prettyprint_rowset(["id"], [(1,)], out)
        text = (tmp_path / "out.txt").read_text()
        # Should start with the margin + header, not a description line
        assert "id" in text.split("\n")[0]

    def test_columns_are_aligned(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.txt")
        prettyprint_rowset(["short", "a_much_longer_column_name"], [("x", "y")], out)
        text = (tmp_path / "out.txt").read_text()
        lines = text.strip().split("\n")
        # Header and data rows should have the same | structure
        header_pipes = lines[0].count("|")
        data_pipes = lines[2].count("|")
        assert header_pipes == data_pipes

    def test_append_mode(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.txt")
        prettyprint_rowset(["col"], [("first",)], out)
        size_after_first = (tmp_path / "out.txt").stat().st_size
        prettyprint_rowset(["col"], [("second",)], out, append=True)
        assert (tmp_path / "out.txt").stat().st_size > size_after_first

    def test_empty_rows(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.txt")
        prettyprint_rowset(["id", "name"], [], out)
        text = (tmp_path / "out.txt").read_text()
        # Header should still be written
        assert "id" in text
        assert "name" in text
