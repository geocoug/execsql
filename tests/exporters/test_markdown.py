"""
Tests for execsql.exporters.markdown — GFM pipe table export.

write_query_to_markdown — GitHub-Flavored Markdown pipe table writer.
"""

from __future__ import annotations

import zipfile
from unittest.mock import MagicMock

import pytest

from execsql.exporters.markdown import write_query_to_markdown


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(headers: list, rows: list) -> MagicMock:
    """Return a mock db whose select_rowsource returns (headers, iter(rows))."""
    db = MagicMock()
    db.select_rowsource.return_value = (headers, iter(rows))
    return db


def _read(path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Basic format
# ---------------------------------------------------------------------------


class TestWriteQueryToMarkdownBasic:
    """Basic GFM pipe table structure."""

    def test_creates_file(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "out.md"
        db = _make_db(["id", "name"], [[1, "Alice"]])
        write_query_to_markdown("SELECT 1", db, str(out))
        assert out.exists()

    def test_header_row_contains_column_names(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "out.md"
        db = _make_db(["id", "name", "score"], [[1, "Alice", 95.2]])
        write_query_to_markdown("SELECT 1", db, str(out))
        text = _read(out)
        assert "| id " in text
        assert "| name " in text
        assert "| score " in text

    def test_separator_row_present(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "out.md"
        db = _make_db(["id", "name"], [[1, "Alice"]])
        write_query_to_markdown("SELECT 1", db, str(out))
        lines = _read(out).splitlines()
        # Second line must be the separator row: all cells consist of dashes
        assert lines[1].startswith("|")
        # Every segment between pipes must be only dashes and spaces
        inner = lines[1].strip("|").split("|")
        for segment in inner:
            assert segment.strip().replace("-", "") == "", f"Bad separator segment: {segment!r}"

    def test_data_rows_present(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "out.md"
        db = _make_db(["id", "name"], [[1, "Alice"], [2, "Bob"]])
        write_query_to_markdown("SELECT 1", db, str(out))
        text = _read(out)
        assert "Alice" in text
        assert "Bob" in text

    def test_row_count_equals_header_plus_sep_plus_data(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "out.md"
        db = _make_db(["id"], [[1], [2], [3]])
        write_query_to_markdown("SELECT 1", db, str(out))
        lines = [ln for ln in _read(out).splitlines() if ln.strip()]
        # header + separator + 3 data rows
        assert len(lines) == 5

    def test_rows_start_and_end_with_pipe(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "out.md"
        db = _make_db(["a", "b"], [[1, 2]])
        write_query_to_markdown("SELECT 1", db, str(out))
        for line in _read(out).splitlines():
            if line.strip():
                assert line.startswith("|"), f"Row does not start with |: {line!r}"
                assert line.endswith("|"), f"Row does not end with |: {line!r}"

    def test_single_column(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "out.md"
        db = _make_db(["val"], [["hello"]])
        write_query_to_markdown("SELECT 1", db, str(out))
        text = _read(out)
        assert "hello" in text
        assert "val" in text

    def test_single_row(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "out.md"
        db = _make_db(["x", "y"], [[42, 99]])
        write_query_to_markdown("SELECT 1", db, str(out))
        lines = [ln for ln in _read(out).splitlines() if ln.strip()]
        assert len(lines) == 3  # header + sep + 1 data row


# ---------------------------------------------------------------------------
# None / empty handling
# ---------------------------------------------------------------------------


class TestNullAndEmptyHandling:
    """None values and empty result sets."""

    def test_none_renders_as_empty_cell(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "out.md"
        db = _make_db(["id", "name"], [[1, None]])
        write_query_to_markdown("SELECT 1", db, str(out))
        text = _read(out)
        # The data row should exist with an empty name cell
        lines = [ln for ln in text.splitlines() if ln.strip()]
        data_row = lines[2]
        # Split on pipe, drop empty first/last elements
        cells = [c.strip() for c in data_row.strip("|").split("|")]
        assert cells[1] == ""  # name column is empty

    def test_empty_result_set_no_data_rows(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "out.md"
        db = _make_db(["id", "name"], [])
        write_query_to_markdown("SELECT 1", db, str(out))
        lines = [ln for ln in _read(out).splitlines() if ln.strip()]
        # Only header + separator, no data rows
        assert len(lines) == 2

    def test_all_none_row(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "out.md"
        db = _make_db(["a", "b", "c"], [[None, None, None]])
        write_query_to_markdown("SELECT 1", db, str(out))
        lines = [ln for ln in _read(out).splitlines() if ln.strip()]
        assert len(lines) == 3
        cells = [c.strip() for c in lines[2].strip("|").split("|")]
        assert all(c == "" for c in cells)


# ---------------------------------------------------------------------------
# Special characters
# ---------------------------------------------------------------------------


class TestSpecialCharacters:
    """Pipe characters and backslashes in data must be escaped."""

    def test_pipe_in_value_is_escaped(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "out.md"
        db = _make_db(["val"], [["a|b"]])
        write_query_to_markdown("SELECT 1", db, str(out))
        text = _read(out)
        # The pipe in the value must be escaped so the table stays valid
        assert r"a\|b" in text

    def test_backslash_in_value_is_escaped(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "out.md"
        db = _make_db(["path"], [[r"C:\Users\foo"]])
        write_query_to_markdown("SELECT 1", db, str(out))
        text = _read(out)
        assert r"\\" in text

    def test_column_count_correct_with_pipe_in_value(self, noop_filewriter_close, tmp_path):
        """Escaped pipes must not increase the apparent column count."""
        out = tmp_path / "out.md"
        db = _make_db(["a", "b"], [["x|y", "z"]])
        write_query_to_markdown("SELECT 1", db, str(out))
        lines = [ln for ln in _read(out).splitlines() if ln.strip()]
        # Each row should have exactly 2 cells (a and b)
        header_cells = lines[0].strip("|").split("|")
        assert len(header_cells) == 2


# ---------------------------------------------------------------------------
# Append mode
# ---------------------------------------------------------------------------


class TestAppendMode:
    """Appending to an existing file."""

    def test_append_adds_content(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "out.md"
        db1 = _make_db(["id"], [[1]])
        write_query_to_markdown("SELECT 1", db1, str(out))
        size1 = out.stat().st_size

        db2 = _make_db(["id"], [[2]])
        write_query_to_markdown("SELECT 1", db2, str(out), append=True)
        assert out.stat().st_size > size1

    def test_append_inserts_blank_separator(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "out.md"
        db1 = _make_db(["id"], [[1]])
        write_query_to_markdown("SELECT 1", db1, str(out))

        db2 = _make_db(["id"], [[2]])
        write_query_to_markdown("SELECT 1", db2, str(out), append=True)
        text = _read(out)
        # There should be at least one blank line separating the two tables
        assert "\n\n" in text


# ---------------------------------------------------------------------------
# desc parameter
# ---------------------------------------------------------------------------


class TestDescParameter:
    """Optional description written as HTML comment."""

    def test_desc_written_as_html_comment(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "out.md"
        db = _make_db(["id"], [[1]])
        write_query_to_markdown("SELECT 1", db, str(out), desc="My Table")
        text = _read(out)
        assert "<!-- My Table -->" in text

    def test_no_desc_no_comment(self, noop_filewriter_close, tmp_path):
        out = tmp_path / "out.md"
        db = _make_db(["id"], [[1]])
        write_query_to_markdown("SELECT 1", db, str(out))
        text = _read(out)
        assert "<!--" not in text


# ---------------------------------------------------------------------------
# Zip output
# ---------------------------------------------------------------------------


class TestZipOutput:
    """Writing into a zip archive."""

    def test_zip_output_creates_archive(self, minimal_conf, tmp_path):
        minimal_conf.zip_buffer_mb = 1
        zip_path = str(tmp_path / "out.zip")
        entry_name = "table.md"
        db = _make_db(["id", "name"], [[1, "Alice"], [2, "Bob"]])
        write_query_to_markdown("SELECT 1", db, entry_name, zipfile=zip_path)
        assert (tmp_path / "out.zip").exists()

    def test_zip_entry_contains_table(self, minimal_conf, tmp_path):
        minimal_conf.zip_buffer_mb = 1
        zip_path = str(tmp_path / "out.zip")
        entry_name = "table.md"
        db = _make_db(["id", "name"], [[1, "Alice"]])
        write_query_to_markdown("SELECT 1", db, entry_name, zipfile=zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            content = zf.read(entry_name).decode("utf-8")
        assert "Alice" in content
        assert "id" in content
        assert "name" in content

    def test_zip_entry_has_valid_separator_row(self, minimal_conf, tmp_path):
        minimal_conf.zip_buffer_mb = 1
        zip_path = str(tmp_path / "out.zip")
        entry_name = "table.md"
        db = _make_db(["col"], [["val"]])
        write_query_to_markdown("SELECT 1", db, entry_name, zipfile=zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            content = zf.read(entry_name).decode("utf-8")
        lines = [ln for ln in content.splitlines() if ln.strip()]
        inner = lines[1].strip("|").split("|")
        for seg in inner:
            assert seg.strip().replace("-", "") == ""


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Database errors are wrapped in ErrInfo."""

    def test_db_error_raises_errinfo(self, noop_filewriter_close, tmp_path):
        from execsql.exceptions import ErrInfo

        out = tmp_path / "out.md"
        db = MagicMock()
        db.select_rowsource.side_effect = RuntimeError("boom")
        with pytest.raises(ErrInfo):
            write_query_to_markdown("SELECT 1", db, str(out))

    def test_errinfo_propagates_unchanged(self, noop_filewriter_close, tmp_path):
        from execsql.exceptions import ErrInfo

        out = tmp_path / "out.md"
        db = MagicMock()
        original = ErrInfo("db", "SELECT 1", exception_msg="original error")
        db.select_rowsource.side_effect = original
        with pytest.raises(ErrInfo) as exc_info:
            write_query_to_markdown("SELECT 1", db, str(out))
        assert exc_info.value is original
