"""Hover explains the metacommand, conditional test or variable under the cursor."""

from __future__ import annotations

import pytest

pytest.importorskip("pygls")

from execsql.lsp.document import index_script  # noqa: E402
from execsql.lsp.hover import hover, metacommand_for  # noqa: E402


def _hover(text: str, path: str | None = None):
    """Hover at the ``|`` in *text*."""
    row = next(n for n, line in enumerate(text.splitlines()) if "|" in line)
    col = text.splitlines()[row].index("|")
    source = text.replace("|", "", 1)
    return hover(index_script(source, path), source, row, col)


@pytest.mark.parametrize(
    ("command", "keyword"),
    [
        ("EXPORT t TO x.csv AS CSV", "EXPORT"),
        ("EXPORT QUERY <<select 1;>> TO x.csv AS CSV", "EXPORT QUERY"),
        ("AUTOCOMMIT ON", "AUTOCOMMIT"),
        ("CONFIG BOOLEAN_INT YES", "CONFIG"),
        ('PROMPT MESSAGE "Sites" MAP sites LAT lat LON lon', "PROMPT MAP"),
        ('PROMPT MESSAGE "hello"', "PROMPT MESSAGE"),
        ("RESET COUNTERS", "RESET COUNTER"),
        ("export t to x.csv as csv", "EXPORT"),
    ],
)
def test_a_line_maps_to_its_metacommand(command, keyword):
    assert metacommand_for(command).keyword == keyword


def test_metacommand_hover_shows_summary_syntax_and_link():
    result = _hover("-- !x! EXP|ORT QUERY <<select 1;>> TO x.csv AS CSV\n")
    value = result.contents.value
    assert value.startswith("**EXPORT QUERY**")
    assert "EXPORT QUERY <<query>>" in value
    assert "/reference/metacommands/#export-query" in value
    assert (result.range.start.character, result.range.end.character) == (7, 19)


def test_condition_hover():
    value = _hover("-- !x! IF(has|rows(orders))\n").contents.value
    assert value.startswith("**HASROWS** — conditional test")
    assert "HASROWS(<table_or_view>)" in value


def test_user_variable_hover_shows_its_definitions():
    text = '-- !x! SUB report_dir /tmp\n-- !x! WRITE "!!report|_dir!!"\n'
    result = _hover(text)
    assert "Defined at line 1" in result.contents.value
    assert "SUB report_dir /tmp" in result.contents.value
    assert (result.range.start.character, result.range.end.character) == (16, 26)


def test_undefined_variable_hover_names_the_rule():
    assert "V001" in _hover("SELECT '!!miss|ing!!';\n").contents.value


def test_system_variable_hover():
    value = _hover("SELECT '!!$CURRENT_DA|TE!!';\n").contents.value
    assert value.startswith("**$CURRENT_DATE** — system variable")
    assert "/reference/substitution_vars/#system_vars" in value


def test_script_parameter_hover():
    text = "-- !x! BEGIN SCRIPT load(table_name)\nSELECT * FROM !!#table|_name!!;\n-- !x! END SCRIPT\n"
    assert "parameter of SCRIPT load" in _hover(text).contents.value


def test_variable_from_an_included_file(tmp_path):
    (tmp_path / "setup.sql").write_text("-- !x! SUB region west\n")
    value = _hover("-- !x! INCLUDE setup.sql\nSELECT '!!reg|ion!!';\n", str(tmp_path / "main.sql")).contents.value
    assert "setup.sql, line 1" in value


def test_nothing_on_plain_sql():
    assert _hover("SELECT co|unt(*) FROM t;\n") is None
