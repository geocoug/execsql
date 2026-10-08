"""Lint findings become diagnostics with a line range, severity, rule code and docs link."""

from __future__ import annotations

import pytest

pytest.importorskip("pygls")

from lsprotocol import types  # noqa: E402

from execsql.lsp.diagnostics import diagnostics  # noqa: E402

SCRIPT = """\
-- !x! SUB report_dir /tmp/reports
    -- !x! EXPROT orders TO out.csv AS CSV
-- !x! IF(hasrowz(orders))
SELECT 1;
-- !x! ENDIF
"""


def _by_code(found):
    return {d.code: d for d in found}


def test_each_finding_underlines_its_line():
    found = _by_code(diagnostics(SCRIPT, None))
    p003 = found["P003"]
    assert p003.range.start == types.Position(line=1, character=4)  # from the first non-blank character
    assert p003.range.end == types.Position(line=1, character=len(SCRIPT.splitlines()[1]))
    assert p003.severity == types.DiagnosticSeverity.Error
    assert "EXPROT" in p003.message
    assert found["P004"].range.start.line == 2
    assert p003.source == "execsql"


def test_warnings_are_warnings_and_link_their_rule():
    found = _by_code(diagnostics(SCRIPT, None))
    v002 = found["V002"]  # report_dir is never used
    assert v002.severity == types.DiagnosticSeverity.Warning
    assert v002.code_description.href.endswith("/reference/lint/#v002")


def test_select_and_ignore_filter_like_execsql_lint():
    assert set(_by_code(diagnostics(SCRIPT, None, select=("P",)))) == {"P003", "P004"}
    assert "V002" not in _by_code(diagnostics(SCRIPT, None, ignore=("V",)))


def test_an_unclosed_block_is_reported_and_the_rest_still_checked():
    found = _by_code(diagnostics("-- !x! IF(hasrows(t))\n-- !x! EXPROT t TO x.csv AS CSV\n", None))
    assert {"P001", "P003"} <= set(found)


def test_include_targets_resolve_next_to_the_file(tmp_path):
    (tmp_path / "setup.sql").write_text("SELECT 1;\n")
    script = tmp_path / "main.sql"
    text = "-- !x! INCLUDE setup.sql\n-- !x! INCLUDE missing.sql\n"
    found = diagnostics(text, str(script))
    assert [(d.code, d.range.start.line) for d in found] == [("I001", 1)]


def test_a_clean_script_has_no_diagnostics():
    assert diagnostics('-- !x! SUB x 1\n-- !x! WRITE "!!x!!"\n', None) == []
