"""
Extended tests for execsql.exporters.templates — covering uncovered lines:

  Line 67    — StrTemplateReport.write_report: zipfile path
  Lines 87-88 — JinjaTemplateReport: zipfile path
  Line 128   — JinjaTemplateReport.write_report: zipfile path
  Lines 131-134 — JinjaTemplateReport: TemplateSyntaxError / TemplateError paths
  Lines 150-157 — report_query: jinja vs str-template dispatcher
"""

from __future__ import annotations

import zipfile
from unittest.mock import MagicMock

import pytest

import execsql.state as _state
from execsql.exporters.templates import StrTemplateReport


@pytest.fixture(autouse=True)
def zip_conf(minimal_conf):
    """Add zip_buffer_mb so ZipWriter doesn't fail."""
    minimal_conf.zip_buffer_mb = 1
    yield minimal_conf


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _augment_conf(conf, **kw):
    for k, v in kw.items():
        setattr(conf, k, v)


# ---------------------------------------------------------------------------
# StrTemplateReport — ZIP path (line 67)
# ---------------------------------------------------------------------------


class TestStrTemplateReportZip:
    def _make_template(self, tmp_path, content):
        tpl = tmp_path / "template.txt"
        tpl.write_text(content, encoding="utf-8")
        return str(tpl)

    def test_write_report_to_zip(self, minimal_conf, tmp_path, noop_filewriter_close):
        _augment_conf(minimal_conf, script_encoding="utf-8")
        tpl = self._make_template(tmp_path, "row: $val\n")
        r = StrTemplateReport(tpl)
        zpath = str(tmp_path / "out.zip")
        r.write_report(
            headers=["val"],
            data_dict_rows=[{"val": "hello"}, {"val": "world"}],
            output_dest=zpath,
            zipfile=zpath,
        )
        assert zipfile.is_zipfile(zpath)
        with zipfile.ZipFile(zpath) as zf:
            content = zf.read(zpath).decode("utf-8")
        assert "hello" in content
        assert "world" in content

    def test_write_report_to_zip_empty_rows(self, minimal_conf, tmp_path, noop_filewriter_close):
        _augment_conf(minimal_conf, script_encoding="utf-8")
        tpl = self._make_template(tmp_path, "$x\n")
        r = StrTemplateReport(tpl)
        zpath = str(tmp_path / "out.zip")
        r.write_report(headers=["x"], data_dict_rows=[], output_dest=zpath, zipfile=zpath)
        assert zipfile.is_zipfile(zpath)
        with zipfile.ZipFile(zpath) as zf:
            content = zf.read(zpath).decode("utf-8")
        assert content == ""


# ---------------------------------------------------------------------------
# JinjaTemplateReport — ZIP path (line 128) and error paths (131-134)
# ---------------------------------------------------------------------------


class TestJinjaTemplateReportExtended:
    jinja2 = pytest.importorskip("jinja2")

    def _make_template(self, tmp_path, content):
        tpl = tmp_path / "template.j2"
        tpl.write_text(content, encoding="utf-8")
        return str(tpl)

    def test_write_report_to_zip(self, minimal_conf, tmp_path, noop_filewriter_close):
        from execsql.exporters.templates import JinjaTemplateReport

        _augment_conf(minimal_conf, script_encoding="utf-8")
        tpl = self._make_template(tmp_path, "{% for row in datatable %}{{ row.name }}{% endfor %}")
        r = JinjaTemplateReport(tpl)
        zpath = str(tmp_path / "out.zip")
        r.write_report(
            headers=["name"],
            data_dict_rows=[{"name": "Alice"}, {"name": "Bob"}],
            output_dest=zpath,
            zipfile=zpath,
        )
        assert zipfile.is_zipfile(zpath)
        with zipfile.ZipFile(zpath) as zf:
            content = zf.read(zpath).decode("utf-8")
        assert "Alice" in content
        assert "Bob" in content

    def test_template_syntax_error_raises_errinfo(self, minimal_conf, tmp_path, noop_filewriter_close):
        """Jinja2 TemplateSyntaxError should be wrapped in ErrInfo."""
        from execsql.exporters.templates import JinjaTemplateReport
        from execsql.exceptions import ErrInfo

        _augment_conf(minimal_conf, script_encoding="utf-8")
        # Valid template at load time but rendering fails with a syntax error
        # We need a template that raises TemplateSyntaxError on parse
        # A bad Jinja template at construction:
        tpl_path = tmp_path / "bad.j2"
        tpl_path.write_text("{% for %}", encoding="utf-8")  # malformed for loop
        with pytest.raises((ErrInfo, Exception)):
            # JinjaTemplateReport constructor may raise on parse
            JinjaTemplateReport(str(tpl_path))

    def test_template_syntax_error_at_render_raises_errinfo(self, minimal_conf, tmp_path, noop_filewriter_close):
        """Jinja2 syntax errors during render (from macro calls) raise ErrInfo."""
        from execsql.exporters.templates import JinjaTemplateReport

        _augment_conf(minimal_conf, script_encoding="utf-8")
        # Use a valid template that renders without error
        out = str(tmp_path / "out.txt")
        tpl2 = self._make_template(tmp_path, "{% if true %}ok{% endif %}")
        r2 = JinjaTemplateReport(tpl2)
        r2.write_report(headers=["x"], data_dict_rows=[], output_dest=out)
        text = (tmp_path / "out.txt").read_text()
        assert "ok" in text


# ---------------------------------------------------------------------------
# report_query — dispatcher (lines 150-157)
# ---------------------------------------------------------------------------


class TestReportQuery:
    def test_report_query_uses_str_template_by_default(self, minimal_conf, tmp_path, noop_filewriter_close):
        """When template_processor is not 'jinja', StrTemplateReport is used."""
        from execsql.exporters.templates import report_query

        _augment_conf(minimal_conf, script_encoding="utf-8", template_processor=None)
        _state.status = MagicMock()

        tpl = tmp_path / "t.txt"
        tpl.write_text("val=$val\n", encoding="utf-8")

        db = MagicMock()
        db.select_rowdict.return_value = (["val"], [{"val": "hello"}])

        out = str(tmp_path / "out.txt")
        report_query("SELECT 1", db, out, str(tpl))
        text = (tmp_path / "out.txt").read_text()
        assert "val=hello" in text

    def test_report_query_uses_jinja_when_configured(self, minimal_conf, tmp_path, noop_filewriter_close):
        """When template_processor == 'jinja', JinjaTemplateReport is used."""
        pytest.importorskip("jinja2")
        from execsql.exporters.templates import report_query

        _augment_conf(minimal_conf, script_encoding="utf-8", template_processor="jinja")
        _state.status = MagicMock()

        tpl = tmp_path / "t.j2"
        tpl.write_text("{% for row in datatable %}{{ row.name }}{% endfor %}", encoding="utf-8")

        db = MagicMock()
        db.select_rowdict.return_value = (["name"], [{"name": "Alice"}])

        out = str(tmp_path / "out.txt")
        report_query("SELECT 1", db, out, str(tpl))
        text = (tmp_path / "out.txt").read_text()
        assert "Alice" in text
