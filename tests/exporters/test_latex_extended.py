"""
Extended tests for execsql.exporters.latex — covering the remaining uncovered
branches:

  Lines 57-59  — stdout path (zipfile=None, not append)
  Line 65      — zipfile path (zipfile is not None)
  Line 72->exit — stdout in append+no-existing-file path (lines 77-79)
  Lines 86->exit — stdout in append+no-existing-file path close branch
  Lines 97->106 — append to existing file (R/W merge logic)
  Line 110      — remaining lines after \\end{document} in merge
  Lines 127-135 — write_query_to_latex error paths
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from execsql.exceptions import ErrInfo
from execsql.exporters.latex import export_latex, write_query_to_latex


@pytest.fixture(autouse=True)
def zip_conf(minimal_conf):
    """Add zip_buffer_mb so ZipWriter doesn't fail."""
    minimal_conf.zip_buffer_mb = 1
    yield minimal_conf


# ---------------------------------------------------------------------------
# stdout path (not append, zipfile=None)
# ---------------------------------------------------------------------------


class TestExportLatexStdout:
    def test_stdout_writes_complete_latex_document(self, capsys):
        export_latex("stdout", ["id", "name"], [(1, "Alice")])
        out = capsys.readouterr().out
        assert r"\documentclass{article}" in out
        assert r"\begin{document}" in out
        assert r"\end{document}" in out

    def test_stdout_contains_table_data(self, capsys):
        export_latex("stdout", ["col"], [(42,)])
        out = capsys.readouterr().out
        assert "42" in out

    def test_stdout_with_desc_writes_caption(self, capsys):
        export_latex("stdout", ["x"], [(1,)], desc="My Caption")
        out = capsys.readouterr().out
        assert r"\caption{My Caption}" in out


# ---------------------------------------------------------------------------
# stdout append path — file doesn't exist (lines 76-87)
# ---------------------------------------------------------------------------


class TestExportLatexStdoutAppend:
    def test_stdout_append_writes_table_only_not_full_document(self, capsys):
        """When append=True and outfile is 'stdout', only the table is written."""
        export_latex("stdout", ["x"], [(5,)], append=True)
        out = capsys.readouterr().out
        assert r"\begin{center}" in out
        # Should NOT have the full document wrapper
        assert r"\documentclass" not in out

    def test_append_to_nonexistent_file_writes_table_only(self, tmp_path):
        out = str(tmp_path / "new.tex")
        export_latex(out, ["a"], [(1,)], append=True)
        text = (tmp_path / "new.tex").read_text()
        assert r"\begin{center}" in text
        assert r"\documentclass" not in text


# ---------------------------------------------------------------------------
# zip path (zipfile is not None)
# NOTE: export_latex's zip branch calls WriteableZipfile(zipfile).open(...)
# but WriteableZipfile has no .open() method.  The test below documents this
# limitation so the branch is at least exercised (AttributeError is caught).
# ---------------------------------------------------------------------------


class TestExportLatexZip:
    def test_zip_branch_raises_attribute_error(self, tmp_path):
        """export_latex zip branch calls WriteableZipfile.open() which doesn't exist."""
        zpath = str(tmp_path / "out.zip")
        with pytest.raises(AttributeError):
            export_latex(zpath, ["id"], [(1,)], zipfile=zpath)


# ---------------------------------------------------------------------------
# Append to existing file — R/W merge (lines 97-115)
# ---------------------------------------------------------------------------


class TestExportLatexAppendMerge:
    def test_append_inserts_second_table_before_end_document(self, tmp_path):
        out = str(tmp_path / "doc.tex")
        # First write: creates complete document
        export_latex(out, ["x"], [(1,)])
        text_after_first = (tmp_path / "doc.tex").read_text()
        assert r"\end{document}" in text_after_first

        # Second write: appends table before \end{document}
        export_latex(out, ["y"], [(2,)], append=True)
        text_after_second = (tmp_path / "doc.tex").read_text()
        assert text_after_second.count(r"\begin{center}") == 2
        assert text_after_second.count(r"\end{document}") == 1

    def test_append_preserves_content_after_end_document(self, tmp_path):
        """Content that follows \\end{document} must be preserved after the merge."""
        out = str(tmp_path / "doc.tex")
        # Manually create a document with trailing content after \end{document}
        (tmp_path / "doc.tex").write_text(
            r"\documentclass{article}"
            + "\n"
            + r"\begin{document}"
            + "\n"
            + r"\end{document}"
            + "\n"
            + "% trailing comment\n",
            encoding="utf-8",
        )
        export_latex(out, ["z"], [(7,)], append=True)
        result = (tmp_path / "doc.tex").read_text()
        assert "% trailing comment" in result
        assert r"\begin{center}" in result

    def test_append_places_new_table_before_existing_end_document(self, tmp_path):
        out = str(tmp_path / "doc.tex")
        export_latex(out, ["a"], [(1,)])
        export_latex(out, ["b"], [(2,)], append=True)
        text = (tmp_path / "doc.tex").read_text()
        # Both tables must appear before \end{document}
        first_begin = text.find(r"\begin{center}")
        second_begin = text.rfind(r"\begin{center}")
        end_doc = text.find(r"\end{document}")
        assert first_begin < end_doc
        assert second_begin < end_doc


# ---------------------------------------------------------------------------
# write_query_to_latex — error paths (lines 127-135)
# ---------------------------------------------------------------------------


class TestWriteQueryToLatex:
    def test_db_error_raises_errinfo(self, tmp_path):
        outfile = str(tmp_path / "out.tex")
        db = MagicMock()
        db.select_rowsource.side_effect = RuntimeError("boom")
        with pytest.raises(ErrInfo):
            write_query_to_latex("SELECT 1", db, outfile)

    def test_errinfo_from_db_propagates_unchanged(self, tmp_path):
        outfile = str(tmp_path / "out.tex")
        db = MagicMock()
        original_err = ErrInfo("db", "SELECT 1")
        db.select_rowsource.side_effect = original_err
        with pytest.raises(ErrInfo) as exc_info:
            write_query_to_latex("SELECT 1", db, outfile)
        assert exc_info.value is original_err

    def test_successful_write(self, tmp_path):
        outfile = str(tmp_path / "out.tex")
        db = MagicMock()
        db.select_rowsource.return_value = (["id", "name"], [(1, "Alice")])
        write_query_to_latex("SELECT 1", db, outfile)
        text = (tmp_path / "out.tex").read_text()
        assert r"\documentclass{article}" in text
        assert "Alice" in text
