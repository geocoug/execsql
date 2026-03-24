"""
Tests for execsql.exporters.templates — template-based report generation.

Covers StrTemplateReport (Python string.Template, no optional deps) and
optionally JinjaTemplateReport when Jinja2 is available.

The ``minimal_conf`` autouse fixture from conftest already sets
``output_encoding``; we augment it with ``script_encoding`` and
``template_processor`` in each test that needs them.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import execsql.state as _state
from execsql.exporters.templates import StrTemplateReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _augment_conf(conf, **kw):
    """Set extra attributes on the conf SimpleNamespace for a single test."""
    for k, v in kw.items():
        setattr(conf, k, v)


# ---------------------------------------------------------------------------
# StrTemplateReport
# ---------------------------------------------------------------------------


class TestStrTemplateReport:
    def _make_template(self, tmp_path, content):
        tpl = tmp_path / "template.txt"
        tpl.write_text(content, encoding="utf-8")
        return str(tpl)

    def test_repr(self, minimal_conf, tmp_path):
        _augment_conf(minimal_conf, script_encoding="utf-8")
        tpl = self._make_template(tmp_path, "Hello $name")
        r = StrTemplateReport(tpl)
        assert tpl in repr(r)

    def test_write_report_single_row(self, minimal_conf, tmp_path, noop_filewriter_close):
        _augment_conf(minimal_conf, script_encoding="utf-8")
        tpl = self._make_template(tmp_path, "id=$id name=$name\n")
        r = StrTemplateReport(tpl)
        out = str(tmp_path / "out.txt")
        r.write_report(
            headers=["id", "name"],
            data_dict_rows=[{"id": 1, "name": "Alice"}],
            output_dest=out,
        )
        text = (tmp_path / "out.txt").read_text()
        assert "id=1" in text
        assert "name=Alice" in text

    def test_write_report_multiple_rows(self, minimal_conf, tmp_path, noop_filewriter_close):
        _augment_conf(minimal_conf, script_encoding="utf-8")
        tpl = self._make_template(tmp_path, "$val\n")
        r = StrTemplateReport(tpl)
        out = str(tmp_path / "out.txt")
        r.write_report(
            headers=["val"],
            data_dict_rows=[{"val": "alpha"}, {"val": "beta"}],
            output_dest=out,
        )
        text = (tmp_path / "out.txt").read_text()
        assert "alpha" in text
        assert "beta" in text

    def test_write_report_empty_rows(self, minimal_conf, tmp_path, noop_filewriter_close):
        _augment_conf(minimal_conf, script_encoding="utf-8")
        tpl = self._make_template(tmp_path, "row: $x\n")
        r = StrTemplateReport(tpl)
        out = str(tmp_path / "out.txt")
        r.write_report(headers=["x"], data_dict_rows=[], output_dest=out)
        text = (tmp_path / "out.txt").read_text()
        assert text == ""

    def test_write_report_append_mode(self, minimal_conf, tmp_path, noop_filewriter_close):
        _augment_conf(minimal_conf, script_encoding="utf-8")
        tpl = self._make_template(tmp_path, "$v\n")
        r = StrTemplateReport(tpl)
        out = str(tmp_path / "out.txt")
        r.write_report(headers=["v"], data_dict_rows=[{"v": "first"}], output_dest=out)
        r.write_report(headers=["v"], data_dict_rows=[{"v": "second"}], output_dest=out, append=True)
        text = (tmp_path / "out.txt").read_text()
        assert "first" in text
        assert "second" in text

    def test_write_report_safe_substitute(self, minimal_conf, tmp_path, noop_filewriter_close):
        """safe_substitute should leave unknown vars as-is rather than raising."""
        _augment_conf(minimal_conf, script_encoding="utf-8")
        tpl = self._make_template(tmp_path, "$known $unknown\n")
        r = StrTemplateReport(tpl)
        out = str(tmp_path / "out.txt")
        r.write_report(headers=["known"], data_dict_rows=[{"known": "hello"}], output_dest=out)
        text = (tmp_path / "out.txt").read_text()
        assert "hello" in text
        # safe_substitute leaves $unknown intact
        assert "$unknown" in text

    def test_write_report_overwrite_mode(self, minimal_conf, tmp_path, noop_filewriter_close):
        _augment_conf(minimal_conf, script_encoding="utf-8")
        tpl = self._make_template(tmp_path, "$v\n")
        r = StrTemplateReport(tpl)
        out = str(tmp_path / "out.txt")
        r.write_report(headers=["v"], data_dict_rows=[{"v": "original"}], output_dest=out)
        r.write_report(headers=["v"], data_dict_rows=[{"v": "replaced"}], output_dest=out, append=False)
        text = (tmp_path / "out.txt").read_text()
        assert "original" not in text
        assert "replaced" in text


# ---------------------------------------------------------------------------
# JinjaTemplateReport (optional — skipped if Jinja2 not installed)
# ---------------------------------------------------------------------------


class TestJinjaTemplateReport:
    jinja2 = pytest.importorskip("jinja2")

    def _make_template(self, tmp_path, content):
        tpl = tmp_path / "template.j2"
        tpl.write_text(content, encoding="utf-8")
        return str(tpl)

    def test_write_report_renders_template(self, minimal_conf, tmp_path, noop_filewriter_close):
        from execsql.exporters.templates import JinjaTemplateReport

        _augment_conf(minimal_conf, script_encoding="utf-8")
        tpl = self._make_template(tmp_path, "{% for row in datatable %}{{ row.name }}\n{% endfor %}")
        r = JinjaTemplateReport(tpl)
        out = str(tmp_path / "out.txt")
        r.write_report(
            headers=["name"],
            data_dict_rows=[{"name": "Alice"}, {"name": "Bob"}],
            output_dest=out,
        )
        text = (tmp_path / "out.txt").read_text()
        assert "Alice" in text
        assert "Bob" in text
