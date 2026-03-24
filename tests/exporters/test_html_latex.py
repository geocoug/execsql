"""
Integration tests for execsql.exporters.html and execsql.exporters.latex.

Both modules write directly to files and depend only on _state.conf and
(for HTML) _state.current_script_line / _state.dbs.current().  All external
state is patched so no database connection is needed.
"""

from __future__ import annotations

import zipfile
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.exporters.html import export_html, export_cgi_html
from execsql.exporters.latex import export_latex


# ---------------------------------------------------------------------------
# Extra conf attributes required by html.py that minimal_conf doesn't provide
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def html_conf(minimal_conf):
    """Extend minimal_conf with attributes needed by the HTML and ZIP exporters."""
    minimal_conf.css_file = None
    minimal_conf.css_styles = None
    minimal_conf.zip_buffer_mb = 1
    yield minimal_conf


@pytest.fixture
def noop_state(noop_filewriter_close):
    """Patch current_script_line and dbs so HTML tests don't need a live DB."""
    fake_db = MagicMock()
    fake_db.name.return_value = "testdb"
    fake_pool = MagicMock()
    fake_pool.current.return_value = fake_db

    with (
        patch("execsql.exporters.html.current_script_line", return_value=("script.sql", 1)),
        patch.object(_state, "dbs", fake_pool),
    ):
        yield


# ===========================================================================
# export_html
# ===========================================================================


class TestExportHtml:
    def test_creates_html_document(self, noop_state, tmp_path):
        out = str(tmp_path / "out.html")
        export_html(out, ["id", "name"], [(1, "Alice"), (2, "Bob")])
        text = (tmp_path / "out.html").read_text()
        assert "<!DOCTYPE html>" in text
        assert "<html>" in text

    def test_contains_table_header_columns(self, noop_state, tmp_path):
        out = str(tmp_path / "out.html")
        export_html(out, ["id", "name"], [(1, "Alice")])
        text = (tmp_path / "out.html").read_text()
        assert "<th>id</th>" in text
        assert "<th>name</th>" in text

    def test_contains_row_data(self, noop_state, tmp_path):
        out = str(tmp_path / "out.html")
        export_html(out, ["id", "name"], [(1, "Alice"), (2, "Bob")])
        text = (tmp_path / "out.html").read_text()
        assert "<td>Alice</td>" in text
        assert "<td>Bob</td>" in text

    def test_caption_written_when_desc_given(self, noop_state, tmp_path):
        out = str(tmp_path / "out.html")
        export_html(out, ["x"], [(1,)], desc="My Table")
        text = (tmp_path / "out.html").read_text()
        assert "<caption>My Table</caption>" in text

    def test_no_caption_when_no_desc(self, noop_state, tmp_path):
        out = str(tmp_path / "out.html")
        export_html(out, ["x"], [(1,)])
        text = (tmp_path / "out.html").read_text()
        assert "<caption>" not in text

    def test_empty_rowset(self, noop_state, tmp_path):
        out = str(tmp_path / "out.html")
        export_html(out, ["id"], [])
        text = (tmp_path / "out.html").read_text()
        assert "<thead>" in text
        assert "<tbody>" in text

    def test_append_new_table_to_existing_file(self, noop_state, tmp_path):
        out = str(tmp_path / "out.html")
        # First write: creates complete HTML document
        export_html(out, ["x"], [(1,)])
        original = (tmp_path / "out.html").read_text()
        assert "</body>" in original
        # Append: inserts second table before </body>
        export_html(out, ["y"], [(2,)], append=True)
        updated = (tmp_path / "out.html").read_text()
        assert updated.count("<table>") == 2

    def test_append_to_nonexistent_file_creates_table_fragment(self, noop_state, tmp_path):
        out = str(tmp_path / "new.html")
        export_html(out, ["col"], [(99,)], append=True)
        text = (tmp_path / "new.html").read_text()
        assert "<table>" in text
        # No full HTML document wrapper
        assert "<!DOCTYPE html>" not in text

    def test_css_file_written_when_configured(self, noop_state, tmp_path, minimal_conf):
        minimal_conf.css_file = "style.css"
        out = str(tmp_path / "out.html")
        export_html(out, ["x"], [(1,)])
        text = (tmp_path / "out.html").read_text()
        assert 'href="style.css"' in text

    def test_css_styles_written_when_configured(self, noop_state, tmp_path, minimal_conf):
        minimal_conf.css_styles = "body { color: red; }"
        out = str(tmp_path / "out.html")
        export_html(out, ["x"], [(1,)])
        text = (tmp_path / "out.html").read_text()
        assert "body { color: red; }" in text

    def test_output_to_zipfile(self, noop_state, tmp_path):
        zpath = str(tmp_path / "out.zip")
        export_html(zpath, ["id"], [(1,)], zipfile=zpath)
        assert zipfile.is_zipfile(zpath)


# ===========================================================================
# export_cgi_html
# ===========================================================================


class TestExportCgiHtml:
    def test_writes_content_type_header(self, noop_state, tmp_path):
        out = str(tmp_path / "out.html")
        export_cgi_html(out, ["id"], [(1,)])
        text = (tmp_path / "out.html").read_text()
        assert "Content-Type: text/html" in text

    def test_contains_table_data(self, noop_state, tmp_path):
        out = str(tmp_path / "out.html")
        export_cgi_html(out, ["id", "val"], [(42, "hello")])
        text = (tmp_path / "out.html").read_text()
        assert "<td>42</td>" in text
        assert "<td>hello</td>" in text

    def test_append_to_existing_file(self, noop_state, tmp_path):
        out = str(tmp_path / "out.html")
        export_cgi_html(out, ["x"], [(1,)])
        export_cgi_html(out, ["x"], [(2,)], append=True)
        text = (tmp_path / "out.html").read_text()
        assert text.count("<table>") == 2

    def test_empty_resultset(self, noop_state, tmp_path):
        out = str(tmp_path / "out.html")
        export_cgi_html(out, ["col"], [])
        text = (tmp_path / "out.html").read_text()
        assert "<table>" in text
        assert "<tbody>" in text


# ===========================================================================
# export_latex
# ===========================================================================


class TestExportLatex:
    def test_creates_latex_document(self, tmp_path):
        out = str(tmp_path / "out.tex")
        export_latex(out, ["id", "name"], [(1, "Alice"), (2, "Bob")])
        text = (tmp_path / "out.tex").read_text()
        assert r"\documentclass{article}" in text
        assert r"\begin{document}" in text
        assert r"\end{document}" in text

    def test_contains_tabular_environment(self, tmp_path):
        out = str(tmp_path / "out.tex")
        export_latex(out, ["a", "b"], [(1, 2)])
        text = (tmp_path / "out.tex").read_text()
        assert r"\begin{tabular}" in text
        assert r"\end{tabular}" in text

    def test_column_headers_in_output(self, tmp_path):
        out = str(tmp_path / "out.tex")
        export_latex(out, ["col_a", "col_b"], [(10, 20)])
        text = (tmp_path / "out.tex").read_text()
        # Underscores in headers are escaped
        assert r"col\_a" in text
        assert r"col\_b" in text

    def test_row_data_in_output(self, tmp_path):
        out = str(tmp_path / "out.tex")
        export_latex(out, ["x"], [(99,)])
        text = (tmp_path / "out.tex").read_text()
        assert "99" in text

    def test_caption_written_when_desc_given(self, tmp_path):
        out = str(tmp_path / "out.tex")
        export_latex(out, ["x"], [(1,)], desc="My Caption")
        text = (tmp_path / "out.tex").read_text()
        assert r"\caption{My Caption}" in text

    def test_no_caption_when_no_desc(self, tmp_path):
        out = str(tmp_path / "out.tex")
        export_latex(out, ["x"], [(1,)])
        text = (tmp_path / "out.tex").read_text()
        assert r"\caption" not in text

    def test_empty_rowset(self, tmp_path):
        out = str(tmp_path / "out.tex")
        export_latex(out, ["a", "b"], [])
        text = (tmp_path / "out.tex").read_text()
        assert r"\begin{tabular}" in text

    def test_append_to_nonexistent_file_writes_table_only(self, tmp_path):
        out = str(tmp_path / "new.tex")
        export_latex(out, ["x"], [(1,)], append=True)
        text = (tmp_path / "new.tex").read_text()
        assert r"\begin{center}" in text
        assert r"\documentclass" not in text

    def test_append_to_existing_file_inserts_before_end_document(self, tmp_path):
        out = str(tmp_path / "out.tex")
        export_latex(out, ["x"], [(1,)])
        export_latex(out, ["y"], [(2,)], append=True)
        text = (tmp_path / "out.tex").read_text()
        assert text.count(r"\begin{center}") == 2

    def test_column_width_matches_header_count(self, tmp_path):
        out = str(tmp_path / "out.tex")
        export_latex(out, ["a", "b", "c"], [(1, 2, 3)])
        text = (tmp_path / "out.tex").read_text()
        # 3 columns → '{ l l l }' in tabular spec
        assert text.count(" l") >= 3
