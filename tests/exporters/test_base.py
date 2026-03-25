"""
Tests for execsql.exporters.base — ExportMetadata, WriteSpec, and ExportRecord.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import execsql.state as _state
from execsql.exporters.base import ExportMetadata, ExportRecord, WriteSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(queryname: str = "q1", filename: str = "out.csv", exported: bool = False):
    """Return a fake ExportRecord-like object without hitting the real constructor."""
    rec = SimpleNamespace(
        exported=exported,
        record=[queryname, filename, None, "/tmp", None, "script.sql", "/tmp", 1, None, "mydb", "localhost", "user"],
    )
    return rec


# ---------------------------------------------------------------------------
# ExportMetadata
# ---------------------------------------------------------------------------


class TestExportMetadata:
    def test_initial_recordlist_empty(self):
        em = ExportMetadata()
        assert em.recordlist == []

    def test_add_appends_record(self):
        em = ExportMetadata()
        r = _make_record()
        em.add(r)
        assert len(em.recordlist) == 1
        assert em.recordlist[0] is r

    def test_add_multiple_records(self):
        em = ExportMetadata()
        em.add(_make_record("q1"))
        em.add(_make_record("q2"))
        em.add(_make_record("q3"))
        assert len(em.recordlist) == 3

    def test_get_returns_colhdrs(self):
        em = ExportMetadata()
        em.add(_make_record())
        colhdrs, _ = em.get()
        assert "query" in colhdrs
        assert "filename" in colhdrs

    def test_get_returns_unexported_records(self):
        em = ExportMetadata()
        em.add(_make_record("q1", exported=False))
        em.add(_make_record("q2", exported=True))
        _, recs = em.get()
        assert len(recs) == 1
        assert recs[0][0] == "q1"

    def test_get_marks_all_as_exported(self):
        em = ExportMetadata()
        r1 = _make_record("q1", exported=False)
        r2 = _make_record("q2", exported=False)
        em.add(r1)
        em.add(r2)
        em.get()
        assert r1.exported is True
        assert r2.exported is True

    def test_get_called_twice_returns_no_new_records_second_time(self):
        em = ExportMetadata()
        em.add(_make_record())
        em.get()
        _, recs = em.get()
        assert recs == []

    def test_get_all_returns_all_regardless_of_exported_flag(self):
        em = ExportMetadata()
        em.add(_make_record("q1", exported=True))
        em.add(_make_record("q2", exported=False))
        _, recs = em.get_all()
        assert len(recs) == 2

    def test_get_all_marks_all_as_exported(self):
        em = ExportMetadata()
        r = _make_record(exported=False)
        em.add(r)
        em.get_all()
        assert r.exported is True

    def test_colhdrs_contains_expected_fields(self):
        expected = {
            "query",
            "filename",
            "zipfilename",
            "file_path",
            "description",
            "script",
            "script_path",
            "script_line",
            "script_date",
            "database",
            "server",
            "username",
        }
        assert set(ExportMetadata.colhdrs) == expected


# ---------------------------------------------------------------------------
# WriteSpec
# ---------------------------------------------------------------------------


class TestWriteSpec:
    def test_init_stores_message(self):
        ws = WriteSpec("hello world")
        assert ws.msg == "hello world"

    def test_init_outfile_none_by_default(self):
        ws = WriteSpec("msg")
        assert ws.outfile is None

    def test_init_outfile_set(self):
        ws = WriteSpec("msg", dest="/tmp/out.txt")
        assert ws.outfile == "/tmp/out.txt"

    def test_init_tee_defaults_false(self):
        ws = WriteSpec("msg")
        assert ws.tee is False

    def test_init_tee_coerced_to_bool(self):
        ws = WriteSpec("msg", tee=1)
        assert ws.tee is True
        ws2 = WriteSpec("msg", tee=0)
        assert ws2.tee is False

    def test_init_repeatable_defaults_false(self):
        ws = WriteSpec("msg")
        assert ws.repeatable is False

    def test_init_written_defaults_false(self):
        ws = WriteSpec("msg")
        assert ws.written is False

    def test_repr_contains_msg(self):
        ws = WriteSpec("my message")
        assert "my message" in repr(ws)

    def test_repr_contains_outfile(self):
        ws = WriteSpec("msg", dest="/tmp/out.txt")
        assert "/tmp/out.txt" in repr(ws)

    def test_repr_format(self):
        ws = WriteSpec("text", dest="file.txt", tee=True)
        r = repr(ws)
        assert r.startswith("WriteSpec(")


# ---------------------------------------------------------------------------
# ExportRecord
# ---------------------------------------------------------------------------


def _fake_db():
    return SimpleNamespace(server_name="localhost", db_name="testdb", user="testuser")


class TestExportRecord:
    def test_init_with_zipfile(self, tmp_path):
        """ExportRecord with zipfile extracts zip parent dir and stores filename."""
        zippath = str(tmp_path / "archive.zip")
        fake_dbs = SimpleNamespace(current=lambda: _fake_db())
        with (
            patch("execsql.exporters.base.current_script_line", return_value=("script.sql", 1)),
            patch.object(_state, "dbs", fake_dbs),
        ):
            rec = ExportRecord("q1", "data.csv", zipfile=zippath)
        # zipfile name stored at index 2
        assert rec.record[2] == "archive.zip"
        # outfile name (inside zip) stored at index 1
        assert rec.record[1] == "data.csv"

    def test_init_without_script_file(self, tmp_path):
        """ExportRecord with None script path sets spath/sname to fallback values."""
        fake_dbs = SimpleNamespace(current=lambda: _fake_db())
        with (
            patch("execsql.exporters.base.current_script_line", return_value=(None, 0)),
            patch.object(_state, "dbs", fake_dbs),
        ):
            rec = ExportRecord("q1", str(tmp_path / "out.csv"))
        # script name should be "<inline>" when script is None
        assert rec.record[5] == "<inline>"
        # script path should be empty
        assert rec.record[6] == ""
