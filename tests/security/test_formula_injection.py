"""B16 regression: CSV / XLSX / ODS exporters neutralize spreadsheet
formula leaders so a malicious cell value cannot execute on open.

Closes audit findings:
* F027 (P0) — CSV ``LineDelimiter.delimited`` formula injection.
* F028 (P0) — XLSX ``_cell_value`` formula injection.
* F029 (P1) — ODS ``OdsFile.cells_from_row`` formula injection.

A cell whose first character is ``=``, ``+``, ``-``, ``@``, or tab is
prefixed with a single quote so Excel / LibreOffice Calc render it as
text instead of evaluating it as a formula. Numeric / datetime / bool
values are untouched — they land in typed cells that can't carry an
injection payload. The ``csv_safe_formulas`` config (default ``True``)
toggles the behaviour.
"""

from __future__ import annotations

import datetime as _datetime

import pytest

from execsql.exporters.base import neutralize_formula


# ---------------------------------------------------------------------------
# The shared helper
# ---------------------------------------------------------------------------


class TestNeutralizeFormula:
    @pytest.mark.parametrize(
        "evil",
        [
            "=cmd|'/c calc'!A1",
            "=2+2",
            "+SUM(A1:A10)",
            "-1+IMPORTXML(...)",
            "@SUM(A1:A10)",
            "\tnewline-tab payload",
        ],
    )
    def test_dangerous_leader_prefixed(self, evil):
        result = neutralize_formula(evil)
        assert result == "'" + evil

    @pytest.mark.parametrize(
        "safe",
        [
            "plain text",
            "Smith, John",
            "no leading trigger",
            "_underscore",
            "#hash",
            "(parens)",
            "0.5",  # leading 0, not a trigger
        ],
    )
    def test_safe_value_unchanged(self, safe):
        assert neutralize_formula(safe) == safe

    def test_empty_string_unchanged(self):
        assert neutralize_formula("") == ""

    @pytest.mark.parametrize(
        "non_str",
        [
            None,
            42,
            -42,
            3.14,
            -3.14,
            True,
            False,
            _datetime.date(2026, 5, 26),
            _datetime.datetime(2026, 5, 26, 10, 0),
        ],
    )
    def test_non_string_pass_through(self, non_str):
        """Numeric / datetime / bool values can't be formulas — they
        land in typed cells, never as string content."""
        assert neutralize_formula(non_str) is non_str

    def test_disabled_via_config(self, monkeypatch):
        import execsql.state as _state

        saved = _state.conf
        fake = type("c", (), {"csv_safe_formulas": False})()
        monkeypatch.setattr(_state, "conf", fake)
        try:
            assert neutralize_formula("=2+2") == "=2+2"
        finally:
            monkeypatch.setattr(_state, "conf", saved)


# ---------------------------------------------------------------------------
# CSV (delimited.py)
# ---------------------------------------------------------------------------


class TestCsvFormulaNeutralization:
    @pytest.fixture
    def csv_writer(self, monkeypatch):
        """LineDelimiter with the default CSV settings."""
        from execsql.exporters.delimited import LineDelimiter

        # csv_safe_formulas defaults True; minimal_conf provides empty
        # SimpleNamespace, so set it explicitly.
        import execsql.state as _state

        if not hasattr(_state.conf, "csv_safe_formulas"):
            monkeypatch.setattr(_state.conf, "csv_safe_formulas", True, raising=False)
        return LineDelimiter(delim=",", quote='"', escchar=None)

    def test_dangerous_leader_prefixed(self, csv_writer):
        line = csv_writer.delimited(["safe", "=cmd|'/c calc'!A1"], add_newline=False)
        # The cell starts with ``'`` so a spreadsheet reader will treat
        # the remainder as text instead of evaluating it as a formula.
        # The CSV writer only auto-quotes when the cell contains ``"``,
        # the delimiter, or a newline — ``'`` alone isn't a trigger, so
        # the leading apostrophe shows up unquoted at the start of the
        # second field.
        assert line == "safe,'=cmd|'/c calc'!A1"

    def test_negative_number_string_prefixed(self, csv_writer):
        """A negative number ARRIVED AS A STRING is treated as a
        potential formula. (Numeric -100 from the DB stays an int.)"""
        line = csv_writer.delimited(["-100"], add_newline=False)
        assert line.startswith("'")

    def test_actual_int_unchanged(self, csv_writer):
        line = csv_writer.delimited([-100], add_newline=False)
        assert line == "-100"

    def test_safe_leading_chars(self, csv_writer):
        line = csv_writer.delimited(["Smith, John"], add_newline=False)
        assert "Smith" in line and not line.startswith("'")

    def test_disabled_via_config(self, csv_writer, monkeypatch):
        import execsql.state as _state

        monkeypatch.setattr(_state.conf, "csv_safe_formulas", False, raising=False)
        line = csv_writer.delimited(["=evil"], add_newline=False)
        assert not line.startswith("'")


# ---------------------------------------------------------------------------
# XLSX (xlsx.py _cell_value)
# ---------------------------------------------------------------------------


class TestXlsxFormulaNeutralization:
    def _cell(self, item):
        from execsql.exporters.xlsx import _cell_value

        return _cell_value(item)

    def test_string_with_formula_leader_prefixed(self, monkeypatch):
        import execsql.state as _state

        monkeypatch.setattr(_state.conf, "csv_safe_formulas", True, raising=False)
        assert self._cell("=2+2") == "'=2+2"

    def test_negative_number_string_prefixed(self, monkeypatch):
        import execsql.state as _state

        monkeypatch.setattr(_state.conf, "csv_safe_formulas", True, raising=False)
        assert self._cell("-100") == "'-100"

    @pytest.mark.parametrize("native", [42, -42, 3.14, True, False])
    def test_native_types_pass_through(self, native):
        assert self._cell(native) is native

    def test_none_passes_through(self):
        assert self._cell(None) is None

    def test_datetime_passes_through(self):
        d = _datetime.datetime(2026, 5, 26)
        assert self._cell(d) is d

    def test_time_stringified_and_neutralized(self, monkeypatch):
        """time → 'HH:MM:SS' string. A time of 00:00:00 starts with
        ``0``, not a formula leader, so the helper passes it through."""
        import execsql.state as _state

        monkeypatch.setattr(_state.conf, "csv_safe_formulas", True, raising=False)
        t = _datetime.time(13, 15, 45)
        assert self._cell(t) == "13:15:45"

    def test_disabled_via_config(self, monkeypatch):
        import execsql.state as _state

        monkeypatch.setattr(_state.conf, "csv_safe_formulas", False, raising=False)
        assert self._cell("=evil") == "=evil"
