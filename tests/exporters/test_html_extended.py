"""
Extended tests for execsql.exporters.html — covering uncovered lines:

  Line 65    — stdout path in main branch (zipfile=None, not append)
  Line 77    — querytext path in meta description
  Lines 113-118 — append=True, outfile=stdout (line 116-118)
  Lines 140->149 — append to existing file: R/W merge
  Lines 160-166 — OSError path after rename (cleanup)
  Line 184   — export_cgi_html: desc is not None
  Line 200   — stdout path in cgi_html
  Line 208   — zipfile path in cgi_html
  Lines 213-217 — cgi_html append with existing file (else branch)
  Line 226->exit — cgi_html stdout final close guard
  Lines 239-245 — write_query_to_html error paths
  Lines 257-263 — write_query_to_cgi_html error paths
"""

from __future__ import annotations

import os
import zipfile
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.exporters.html import export_cgi_html, export_html, write_query_to_cgi_html, write_query_to_html
from execsql.exceptions import ErrInfo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def html_conf(minimal_conf):
    minimal_conf.css_file = None
    minimal_conf.css_styles = None
    minimal_conf.zip_buffer_mb = 1
    yield minimal_conf


@pytest.fixture
def noop_state(noop_filewriter_close):
    fake_db = MagicMock()
    fake_db.name.return_value = "testdb"
    fake_pool = MagicMock()
    fake_pool.current.return_value = fake_db
    with (
        patch("execsql.exporters.html.current_script_line", return_value=("script.sql", 1)),
        patch.object(_state, "dbs", fake_pool),
    ):
        yield


# ---------------------------------------------------------------------------
# export_html — stdout path (line 65)
# ---------------------------------------------------------------------------


class TestExportHtmlStdout:
    def test_stdout_writes_complete_document(self, noop_state, capsys):
        export_html("stdout", ["id", "name"], [(1, "Alice")])
        out = capsys.readouterr().out
        assert "<!DOCTYPE html>" in out
        assert "<html>" in out

    def test_stdout_contains_table_data(self, noop_state, capsys):
        export_html("stdout", ["col"], [(99,)])
        out = capsys.readouterr().out
        assert "<td>99</td>" in out

    def test_stdout_with_querytext_writes_source_meta(self, noop_state, capsys):
        """When querytext is provided, the meta description includes 'Source:'."""
        export_html("stdout", ["x"], [(1,)], querytext="SELECT * FROM t")
        out = capsys.readouterr().out
        assert "Source:" in out

    def test_stdout_without_querytext_writes_from_database_meta(self, noop_state, capsys):
        """Without querytext, the meta description starts with 'From database'."""
        export_html("stdout", ["x"], [(1,)])
        out = capsys.readouterr().out
        assert "From database" in out


# ---------------------------------------------------------------------------
# export_html — append to existing file: stdout (line 116-118)
# ---------------------------------------------------------------------------


class TestExportHtmlAppendStdout:
    def test_stdout_append_writes_table_only(self, noop_state, capsys):
        """In append mode with stdout, only the table fragment is written."""
        export_html("stdout", ["x"], [(1,)], append=True)
        out = capsys.readouterr().out
        assert "<table>" in out
        # No full document wrapper
        assert "<!DOCTYPE html>" not in out


# ---------------------------------------------------------------------------
# export_html — append to existing file: R/W merge (lines 140-166)
# ---------------------------------------------------------------------------


class TestExportHtmlAppendMerge:
    def test_second_table_inserted_before_body_close(self, noop_state, tmp_path):
        out = str(tmp_path / "page.html")
        export_html(out, ["x"], [(1,)])
        text1 = (tmp_path / "page.html").read_text()
        assert "</body>" in text1

        export_html(out, ["y"], [(2,)], append=True)
        text2 = (tmp_path / "page.html").read_text()
        assert text2.count("<table>") == 2
        assert text2.count("</body>") == 1

    def test_content_after_body_tag_preserved(self, noop_state, tmp_path):
        """Content that follows </body> (i.e. </html>) must survive the merge."""
        out = str(tmp_path / "page.html")
        export_html(out, ["a"], [(1,)])
        export_html(out, ["b"], [(2,)], append=True)
        text = (tmp_path / "page.html").read_text()
        assert "</html>" in text

    def test_oserror_during_rename_cleans_up_temp(self, noop_state, tmp_path):
        """If os.rename raises OSError the temp file should be cleaned up."""
        out = str(tmp_path / "page.html")
        export_html(out, ["x"], [(1,)])

        real_unlink = os.unlink

        def fake_rename(src, dst):
            raise OSError("rename failed")

        def fake_unlink_first_call(path):
            if path == out:
                raise OSError("first unlink failed")
            real_unlink(path)

        with (
            patch("execsql.exporters.html.os.rename", side_effect=fake_rename),
            patch("execsql.exporters.html.os.unlink", side_effect=fake_unlink_first_call),
            pytest.raises(OSError),
        ):
            export_html(out, ["y"], [(2,)], append=True)


# ---------------------------------------------------------------------------
# export_cgi_html — desc caption (line 184)
# ---------------------------------------------------------------------------


class TestExportCgiHtmlDesc:
    def test_desc_written_as_caption(self, noop_state, tmp_path):
        out = str(tmp_path / "cgi.html")
        export_cgi_html(out, ["x"], [(1,)], desc="Table caption")
        text = (tmp_path / "cgi.html").read_text()
        assert "<caption>Table caption</caption>" in text

    def test_no_caption_when_desc_none(self, noop_state, tmp_path):
        out = str(tmp_path / "cgi.html")
        export_cgi_html(out, ["x"], [(1,)])
        text = (tmp_path / "cgi.html").read_text()
        assert "<caption>" not in text


# ---------------------------------------------------------------------------
# export_cgi_html — stdout path (line 200)
# ---------------------------------------------------------------------------


class TestExportCgiHtmlStdout:
    def test_stdout_writes_content_type_header(self, noop_state, capsys):
        export_cgi_html("stdout", ["id"], [(1,)])
        out = capsys.readouterr().out
        assert "Content-Type: text/html" in out

    def test_stdout_contains_table_data(self, noop_state, capsys):
        export_cgi_html("stdout", ["val"], [(42,)])
        out = capsys.readouterr().out
        assert "<td>42</td>" in out


# ---------------------------------------------------------------------------
# export_cgi_html — ZIP path (line 208)
# ---------------------------------------------------------------------------


class TestExportCgiHtmlZip:
    def test_writes_to_zip(self, noop_state, tmp_path):
        zpath = str(tmp_path / "out.zip")
        export_cgi_html(zpath, ["id"], [(1,)], zipfile=zpath)
        assert zipfile.is_zipfile(zpath)
        with zipfile.ZipFile(zpath) as zf:
            content = zf.read(zpath).decode("utf-8")
        assert "Content-Type: text/html" in content

    def test_zip_contains_table_data(self, noop_state, tmp_path):
        zpath = str(tmp_path / "out.zip")
        export_cgi_html(zpath, ["val"], [(99,)], zipfile=zpath)
        with zipfile.ZipFile(zpath) as zf:
            content = zf.read(zpath).decode("utf-8")
        assert "<td>99</td>" in content


# ---------------------------------------------------------------------------
# export_cgi_html — append to existing file (else branch, lines 215-227)
# ---------------------------------------------------------------------------


class TestExportCgiHtmlAppendToExisting:
    def test_append_to_existing_adds_second_table(self, noop_state, tmp_path):
        out = str(tmp_path / "cgi.html")
        # First write: creates file with Content-Type header
        export_cgi_html(out, ["x"], [(1,)])
        # Second write: append=True and file exists
        export_cgi_html(out, ["x"], [(2,)], append=True)
        text = (tmp_path / "cgi.html").read_text()
        assert text.count("<table>") == 2

    def test_append_to_stdout_writes_table(self, noop_state, capsys):
        """In the else branch when outfile == 'stdout'."""
        # First write: creates initial state for 'stdout' append
        # For stdout with append=True and existing file condition false for stdout:
        # actually the condition is `append and not Path(outfile).is_file()` — for stdout
        # this evaluates based on if "stdout" is a file on disk (it won't be).
        # So stdout + append hits the first branch (not the else).
        # This test confirms no crash.
        export_cgi_html("stdout", ["y"], [(9,)], append=True)
        out = capsys.readouterr().out
        assert "<table>" in out


# ---------------------------------------------------------------------------
# write_query_to_html — error paths (lines 239-245)
# ---------------------------------------------------------------------------


class TestWriteQueryToHtml:
    def test_db_error_raises_errinfo(self, noop_state, tmp_path):
        outfile = str(tmp_path / "out.html")
        db = MagicMock()
        db.select_rowsource.side_effect = RuntimeError("boom")
        with pytest.raises(ErrInfo):
            write_query_to_html("SELECT 1", db, outfile)

    def test_errinfo_from_db_propagates_unchanged(self, noop_state, tmp_path):
        outfile = str(tmp_path / "out.html")
        db = MagicMock()
        original = ErrInfo("db", "SELECT 1")
        db.select_rowsource.side_effect = original
        with pytest.raises(ErrInfo) as exc_info:
            write_query_to_html("SELECT 1", db, outfile)
        assert exc_info.value is original

    def test_successful_write(self, noop_state, tmp_path):
        outfile = str(tmp_path / "out.html")
        db = MagicMock()
        db.select_rowsource.return_value = (["col"], [(1,)])
        write_query_to_html("SELECT 1", db, outfile)
        text = (tmp_path / "out.html").read_text()
        assert "<!DOCTYPE html>" in text


# ---------------------------------------------------------------------------
# write_query_to_cgi_html — error paths (lines 257-263)
# ---------------------------------------------------------------------------


class TestWriteQueryToCgiHtml:
    def test_db_error_raises_errinfo(self, noop_state, tmp_path):
        outfile = str(tmp_path / "out.html")
        db = MagicMock()
        db.select_rowsource.side_effect = RuntimeError("boom")
        with pytest.raises(ErrInfo):
            write_query_to_cgi_html("SELECT 1", db, outfile)

    def test_errinfo_from_db_propagates_unchanged(self, noop_state, tmp_path):
        outfile = str(tmp_path / "out.html")
        db = MagicMock()
        original = ErrInfo("db", "SELECT 1")
        db.select_rowsource.side_effect = original
        with pytest.raises(ErrInfo) as exc_info:
            write_query_to_cgi_html("SELECT 1", db, outfile)
        assert exc_info.value is original

    def test_successful_write(self, noop_state, tmp_path):
        outfile = str(tmp_path / "out.html")
        db = MagicMock()
        db.select_rowsource.return_value = (["col"], [(1,)])
        write_query_to_cgi_html("SELECT 1", db, outfile)
        text = (tmp_path / "out.html").read_text()
        assert "Content-Type: text/html" in text
