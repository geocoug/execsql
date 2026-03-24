"""
Tests for execsql.exporters.json — JSON export functions.

write_query_to_json  — JSON array-of-objects
write_query_to_json_ts — JSON with top-level timestamp-style wrapper
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from execsql.exporters.json import write_query_to_json, write_query_to_json_ts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(headers, rows):
    """Return a mock db whose select_rowsource returns (headers, rows)."""
    db = MagicMock()
    db.select_rowsource.return_value = (headers, rows)
    return db


# ---------------------------------------------------------------------------
# write_query_to_json
# ---------------------------------------------------------------------------


class TestWriteQueryToJson:
    def test_creates_valid_json_array(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.json")
        db = _make_db(["id", "name"], [[1, "Alice"], [2, "Bob"]])
        write_query_to_json("SELECT 1", db, outfile)
        data = json.loads((tmp_path / "out.json").read_text())
        assert isinstance(data, list)
        assert len(data) == 2

    def test_keys_match_headers(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.json")
        db = _make_db(["id", "name"], [[1, "Alice"]])
        write_query_to_json("SELECT 1", db, outfile)
        data = json.loads((tmp_path / "out.json").read_text())
        assert set(data[0].keys()) == {"id", "name"}

    def test_values_serialized(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.json")
        db = _make_db(["x"], [[42]])
        write_query_to_json("SELECT 1", db, outfile)
        data = json.loads((tmp_path / "out.json").read_text())
        assert data[0]["x"] == 42

    def test_none_values_serialized_as_null(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.json")
        db = _make_db(["x"], [[None]])
        write_query_to_json("SELECT 1", db, outfile)
        data = json.loads((tmp_path / "out.json").read_text())
        assert data[0]["x"] is None

    def test_empty_result_produces_empty_array(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.json")
        db = _make_db(["id"], [])
        write_query_to_json("SELECT 1", db, outfile)
        data = json.loads((tmp_path / "out.json").read_text())
        assert data == []

    def test_append_mode_adds_separator(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.json")
        db = _make_db(["id"], [[1]])
        write_query_to_json("SELECT 1", db, outfile)
        size1 = (tmp_path / "out.json").stat().st_size
        db2 = _make_db(["id"], [[2]])
        write_query_to_json("SELECT 1", db2, outfile, append=True)
        assert (tmp_path / "out.json").stat().st_size > size1

    def test_multiple_columns(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.json")
        db = _make_db(["a", "b", "c"], [[1, 2, 3]])
        write_query_to_json("SELECT 1", db, outfile)
        data = json.loads((tmp_path / "out.json").read_text())
        assert data[0] == {"a": 1, "b": 2, "c": 3}

    def test_string_values_stay_strings(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.json")
        db = _make_db(["name"], [["hello"]])
        write_query_to_json("SELECT 1", db, outfile)
        data = json.loads((tmp_path / "out.json").read_text())
        assert data[0]["name"] == "hello"

    def test_db_error_raises(self, noop_filewriter_close, tmp_path):
        from execsql.exceptions import ErrInfo

        outfile = str(tmp_path / "out.json")
        db = MagicMock()
        db.select_rowsource.side_effect = RuntimeError("boom")
        with pytest.raises(ErrInfo):
            write_query_to_json("SELECT 1", db, outfile)


# ---------------------------------------------------------------------------
# write_query_to_json_ts (write_types=False to avoid _state.to_json_type)
# ---------------------------------------------------------------------------


class TestWriteQueryToJsonTs:
    def test_produces_object_with_fields_key(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.json")
        db = _make_db(["id", "name"], [[1, "Alice"]])
        write_query_to_json_ts("SELECT 1", db, outfile, write_types=False)
        text = (tmp_path / "out.json").read_text()
        assert '"fields"' in text

    def test_field_names_in_output(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.json")
        db = _make_db(["alpha", "beta"], [[1, 2]])
        write_query_to_json_ts("SELECT 1", db, outfile, write_types=False)
        text = (tmp_path / "out.json").read_text()
        assert "alpha" in text
        assert "beta" in text

    def test_desc_written_when_provided(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.json")
        db = _make_db(["id"], [[1]])
        write_query_to_json_ts("SELECT 1", db, outfile, desc="My query", write_types=False)
        text = (tmp_path / "out.json").read_text()
        assert "My query" in text

    def test_no_desc_no_description_key(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.json")
        db = _make_db(["id"], [[1]])
        write_query_to_json_ts("SELECT 1", db, outfile, write_types=False)
        text = (tmp_path / "out.json").read_text()
        assert '"description"' not in text

    def test_append_mode_prepends_comma(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.json")
        db = _make_db(["id"], [[1]])
        write_query_to_json_ts("SELECT 1", db, outfile, write_types=False)
        size1 = (tmp_path / "out.json").stat().st_size
        db2 = _make_db(["id"], [[2]])
        write_query_to_json_ts("SELECT 1", db2, outfile, append=True, write_types=False)
        assert (tmp_path / "out.json").stat().st_size > size1

    def test_title_is_capitalized_column_name(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.json")
        db = _make_db(["my_col"], [[1]])
        write_query_to_json_ts("SELECT 1", db, outfile, write_types=False)
        text = (tmp_path / "out.json").read_text()
        assert "My col" in text

    def test_db_error_raises(self, noop_filewriter_close, tmp_path):
        from execsql.exceptions import ErrInfo

        outfile = str(tmp_path / "out.json")
        db = MagicMock()
        db.select_rowsource.side_effect = RuntimeError("boom")
        with pytest.raises(ErrInfo):
            write_query_to_json_ts("SELECT 1", db, outfile, write_types=False)
