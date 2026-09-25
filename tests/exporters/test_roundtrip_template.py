"""
Template-report round trips, driven by a real database.

``report_query`` renders database values through a user-supplied Jinja2
template. The sandbox it uses guards against a hostile *template*; nothing
guarded against hostile *data*, so a value containing ``<script>`` rendered
into an HTML report as live markup.

Autoescaping is now chosen by the template's extension, so these tests check
both halves of that: an ``.html`` template escapes, and a ``.csv`` or ``.tex``
one is left exactly as it was.
"""

from __future__ import annotations

import pytest

import execsql.state as _state
from execsql.config import StatObj

from .conftest import TABLE_NAME

pytest.importorskip("jinja2", reason="requires jinja2 (execsql2[formats])")

from execsql.exporters.templates import report_query  # noqa: E402

MARKUP = '<b>a & b</b> | "pipe" <script>'
BODY = "{% for r in datatable %}{{ r.t_markup }}{% endfor %}"


@pytest.fixture
def jinja_ready(export_db):
    """report_query reads _state.status, which a bare fixture does not set."""
    _state.status = StatObj()
    _state.conf.template_processor = "jinja"
    return export_db


def _render(db, tmp_path, extension, body=BODY, column="t_markup"):
    template = tmp_path / f"report.{extension}"
    template.write_text(body, encoding="utf-8")
    out = tmp_path / f"out.{extension}"
    report_query(f"select * from {TABLE_NAME} where id = 1;", db, str(out), str(template))
    return out.read_text(encoding="utf-8").strip()


class TestHtmlTemplatesEscapeData:
    """A value from the database must not become markup in an HTML report."""

    def test_script_tag_is_escaped(self, jinja_ready, tmp_path):
        rendered = _render(jinja_ready, tmp_path, "html")
        assert "<script>" not in rendered, "database value rendered as live markup"
        assert "&lt;script&gt;" in rendered

    def test_ampersand_is_escaped(self, jinja_ready, tmp_path):
        assert "&amp;" in _render(jinja_ready, tmp_path, "html")

    def test_htm_extension_is_also_escaped(self, jinja_ready, tmp_path):
        assert "<script>" not in _render(jinja_ready, tmp_path, "htm")

    def test_xml_extension_is_also_escaped(self, jinja_ready, tmp_path):
        assert "<script>" not in _render(jinja_ready, tmp_path, "xml")

    def test_a_template_can_still_ask_for_raw_markup(self, jinja_ready, tmp_path):
        """`|safe` is the opt-out for a template that means to emit HTML."""
        body = "{% for r in datatable %}{{ r.t_markup|safe }}{% endfor %}"
        assert "<script>" in _render(jinja_ready, tmp_path, "html", body=body)


class TestNonMarkupTemplatesAreUnchanged:
    """Only markup extensions changed; every other template renders as before.

    Escaping a CSV or LaTeX template would corrupt it — ``&`` is meaningful in
    LaTeX and ``&amp;`` is not what belongs in a CSV cell.
    """

    @pytest.mark.parametrize("extension", ["csv", "tex", "txt", "sql", "md"])
    def test_data_is_rendered_verbatim(self, jinja_ready, tmp_path, extension):
        assert _render(jinja_ready, tmp_path, extension) == MARKUP


class TestTemplateDataFidelity:
    def test_unicode_survives(self, jinja_ready, tmp_path):
        body = "{% for r in datatable %}{{ r.t_unicode }}{% endfor %}"
        assert _render(jinja_ready, tmp_path, "txt", body=body) == "café — naïve ± 30° ⚡"

    def test_zero_is_rendered(self, jinja_ready, tmp_path):
        """A falsy value is still a value."""
        body = "{% for r in datatable %}[{{ r.n_zero }}]{% endfor %}"
        assert _render(jinja_ready, tmp_path, "txt", body=body) == "[0]"

    def test_numeric_keeps_its_value(self, jinja_ready, tmp_path):
        body = "{% for r in datatable %}{{ r.n_dec }}{% endfor %}"
        assert "1234.567" in _render(jinja_ready, tmp_path, "txt", body=body)

    def test_headers_are_available_to_the_template(self, jinja_ready, tmp_path):
        body = "{{ headers|join(',') }}"
        assert "t_markup" in _render(jinja_ready, tmp_path, "txt", body=body)
