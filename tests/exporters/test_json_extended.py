"""
Extended tests for execsql.exporters.json — covering uncovered lines:

  Line 37    — filewriter_close called; write append comma (line 47)
  Line 51    — ZIP path for write_query_to_json
  Line 84    — write_query_to_json_ts: filewriter_close; append comma (line 95)
  Line 99    — ZIP path for write_query_to_json_ts
  Lines 108-114 — write_types=True branch (DataTable-based type inference)
"""

from __future__ import annotations

import json
import zipfile
from unittest.mock import MagicMock

import pytest

import execsql.state as _state
from execsql.exporters.json import write_query_to_json, write_query_to_json_ts


@pytest.fixture(autouse=True)
def zip_conf(minimal_conf):
    """Add zip_buffer_mb so ZipWriter doesn't fail."""
    minimal_conf.zip_buffer_mb = 1
    yield minimal_conf


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(headers, rows):
    db = MagicMock()
    db.select_rowsource.return_value = (headers, rows)
    return db


# ---------------------------------------------------------------------------
# write_query_to_json — ZIP path (line 51)
# ---------------------------------------------------------------------------


class TestWriteQueryToJsonZip:
    def test_writes_json_array_to_zip(self, noop_filewriter_close, tmp_path):
        zpath = str(tmp_path / "out.zip")
        db = _make_db(["id", "name"], [[1, "Alice"], [2, "Bob"]])
        write_query_to_json("SELECT 1", db, zpath, zipfile=zpath)
        assert zipfile.is_zipfile(zpath)
        with zipfile.ZipFile(zpath) as zf:
            content = zf.read(zf.namelist()[0]).decode("utf-8")
        data = json.loads(content)
        assert len(data) == 2
        assert data[0]["id"] == 1

    def test_zip_empty_result(self, noop_filewriter_close, tmp_path):
        zpath = str(tmp_path / "out.zip")
        db = _make_db(["id"], [])
        write_query_to_json("SELECT 1", db, zpath, zipfile=zpath)
        with zipfile.ZipFile(zpath) as zf:
            content = zf.read(zf.namelist()[0]).decode("utf-8")
        data = json.loads(content)
        assert data == []

    def test_zip_append_mode(self, noop_filewriter_close, tmp_path):
        """Append mode with zip should grow the archive."""
        zpath = str(tmp_path / "out.zip")
        db1 = _make_db(["id"], [[1]])
        write_query_to_json("SELECT 1", db1, zpath, zipfile=zpath)
        size1 = (tmp_path / "out.zip").stat().st_size
        db2 = _make_db(["id"], [[2]])
        write_query_to_json("SELECT 1", db2, zpath, append=True, zipfile=zpath)
        assert (tmp_path / "out.zip").stat().st_size > size1


# ---------------------------------------------------------------------------
# write_query_to_json_ts — ZIP path (line 99)
# ---------------------------------------------------------------------------


class TestWriteQueryToJsonTsZip:
    def test_writes_ts_structure_to_zip(self, noop_filewriter_close, tmp_path):
        zpath = str(tmp_path / "out.zip")
        db = _make_db(["id", "name"], [[1, "Alice"]])
        write_query_to_json_ts("SELECT 1", db, zpath, zipfile=zpath, write_types=False)
        with zipfile.ZipFile(zpath) as zf:
            content = zf.read(zf.namelist()[0]).decode("utf-8")
        assert '"fields"' in content
        assert "id" in content

    def test_zip_with_desc(self, noop_filewriter_close, tmp_path):
        zpath = str(tmp_path / "out.zip")
        db = _make_db(["x"], [[1]])
        write_query_to_json_ts("SELECT 1", db, zpath, zipfile=zpath, write_types=False, desc="A description")
        with zipfile.ZipFile(zpath) as zf:
            content = zf.read(zf.namelist()[0]).decode("utf-8")
        assert "A description" in content


# ---------------------------------------------------------------------------
# write_query_to_json_ts — write_types=True (lines 108-114)
# Requires _state.to_json_type to be populated (it is by models module).
# ---------------------------------------------------------------------------


class TestWriteQueryToJsonTsWriteTypes:
    def test_write_types_true_includes_type_field(self, noop_filewriter_close, tmp_path):
        """write_types=True uses DataTable to infer types and writes a 'type' key."""
        # Ensure to_json_type is populated
        from execsql.models import to_json_type as tjt

        _state.to_json_type = tjt

        outfile = str(tmp_path / "out.json")
        db = _make_db(["id", "name"], [[1, "Alice"], [2, "Bob"]])
        write_query_to_json_ts("SELECT 1", db, outfile, write_types=True)
        text = (tmp_path / "out.json").read_text()
        assert '"type"' in text

    def test_write_types_true_field_names_present(self, noop_filewriter_close, tmp_path):
        from execsql.models import to_json_type as tjt

        _state.to_json_type = tjt

        outfile = str(tmp_path / "out.json")
        db = _make_db(["alpha", "beta"], [[1, 2.5]])
        write_query_to_json_ts("SELECT 1", db, outfile, write_types=True)
        text = (tmp_path / "out.json").read_text()
        assert "alpha" in text
        assert "beta" in text

    def test_write_types_true_title_capitalized(self, noop_filewriter_close, tmp_path):
        from execsql.models import to_json_type as tjt

        _state.to_json_type = tjt

        outfile = str(tmp_path / "out.json")
        db = _make_db(["my_col"], [[42]])
        write_query_to_json_ts("SELECT 1", db, outfile, write_types=True)
        text = (tmp_path / "out.json").read_text()
        assert "My col" in text

    def test_write_types_true_with_single_column(self, noop_filewriter_close, tmp_path):
        """Single column — no trailing comma in JSON fields array."""
        from execsql.models import to_json_type as tjt

        _state.to_json_type = tjt

        outfile = str(tmp_path / "out.json")
        db = _make_db(["score"], [[100]])
        write_query_to_json_ts("SELECT 1", db, outfile, write_types=True)
        text = (tmp_path / "out.json").read_text()
        assert '"fields"' in text
        assert "score" in text

    def test_write_types_true_empty_rows(self, noop_filewriter_close, tmp_path):
        """write_types=True with zero rows should still produce a valid schema."""
        from execsql.models import to_json_type as tjt

        _state.to_json_type = tjt

        outfile = str(tmp_path / "out.json")
        db = _make_db(["col"], [])
        write_query_to_json_ts("SELECT 1", db, outfile, write_types=True)
        text = (tmp_path / "out.json").read_text()
        assert '"fields"' in text
