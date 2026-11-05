"""Condition errors name the script problem consistently in the run, lint and LSP."""

from __future__ import annotations

import pytest

from execsql import run
from execsql.cli.lint import lint_source
from execsql.exceptions import CondParserError
from execsql.metacommands.conditions import CONDITIONAL_TABLE
from execsql.parser import CondParser


def _message(condition):
    with pytest.raises(CondParserError) as caught:
        CondParser(condition, CONDITIONAL_TABLE).parse()
    return str(caught.value)


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        ("NO_SUCH_FN(x)", "Unknown condition test: NO_SUCH_FN"),
        ("NOT_A_TEST(x)", "Unknown condition test: NOT_A_TEST"),
        ("TRUE AND NO_SUCH_FN(x)", "Unknown condition test: NO_SUCH_FN"),
        ("HAS_ROWZ(orders)", "did you mean HASROWS?"),
        ("IS_GT(1 2)", "Separate the arguments of IS_GT with a comma"),
        ("TABLE_EXISTS(t", "Missing ')' in condition"),
        ("(TRUE", "Missing ')' in condition"),
        ("TRUE)", "Unexpected ')' in condition"),
        ("TRUE FALSE", "Expected AND or OR"),
        ("(TRUE FALSE)", "Expected AND or OR"),
        ("TRUE AND", "Expected a condition test"),
        ("!!flag!! = TRUE", "compare values with EQUALS(a, b) or IS_TRUE(x)"),
        ("TRUE = FALSE", "compare values with EQUALS(a, b) or IS_TRUE(x)"),
        ("ready = TRUE", "compare values with EQUALS(a, b) or IS_TRUE(x)"),
        ("NO_LABEL = TRUE", "compare values with EQUALS(a, b) or IS_TRUE(x)"),
        ("HAS_ROWS()", "Invalid syntax for HAS_ROWS"),
        ("EQUALS(one two)", "Separate the arguments of EQUALS with a comma"),
        ('EQUALS("(" 1 2)', "Separate the arguments of EQUALS with a comma"),
        ('IS_GT("unfinished 2)', "Missing closing quote"),
    ],
)
def test_errors_explain_the_problem(condition, expected):
    assert expected in _message(condition)


@pytest.mark.parametrize("condition", ["hasrowz(t)", "IS_GT(1 2)", "TABLE_EXISTS(t", "!!flag!! = TRUE"])
def test_lint_uses_the_parser_message_with_original_variables(condition):
    source = f"-- !x! IF ({condition})\n-- !x! ENDIF\n"
    issues = [issue for issue in lint_source(source, "test.sql") if issue.code == "P004"]
    assert len(issues) == 1
    assert issues[0].message == _message(condition)
    assert issues[0].line == 1


@pytest.mark.parametrize("condition", ["HAS_ROWZ(t)", "IS_GT(1 2)"])
@pytest.mark.parametrize(
    "source",
    [
        '-- !x! IF (HAS_ROWZ(t)) { WRITE "ran" }\n',
        '-- !x! IF (HAS_ROWZ(t))\n-- !x! WRITE "ran"\n-- !x! ENDIF\n',
        "-- !x! IF (FALSE)\n-- !x! ELSEIF (HAS_ROWZ(t))\n-- !x! ENDIF\n",
        "-- !x! IF (TRUE)\n-- !x! ANDIF (HAS_ROWZ(t))\n-- !x! ENDIF\n",
        "-- !x! IF (FALSE)\n-- !x! ORIF (HAS_ROWZ(t))\n-- !x! ENDIF\n",
        "-- !x! LOOP WHILE (HAS_ROWZ(t))\n-- !x! END LOOP\n",
        "-- !x! BEGIN SCRIPT s\n-- !x! END SCRIPT\n-- !x! EXECUTE SCRIPT s WHILE (HAS_ROWZ(t))\n",
        "-- !x! ASSERT HAS_ROWZ(t)\n",
        "-- !x! WAIT_UNTIL HAS_ROWZ(t) CONTINUE AFTER 1 SECONDS\n",
    ],
)
def test_every_condition_site_reports_the_same_error_and_still_halts(source, condition):
    source = source.replace("HAS_ROWZ(t)", condition)
    source = "-- !x! METACOMMAND_ERROR_HALT OFF\n" + source + "-- !x! SUB reached yes\n"
    result = run(sql=source, dsn="sqlite:///:memory:")
    assert not result.success
    assert len(result.errors) == 1
    assert "CondParserError: " + _message(condition) in result.errors[0].message
    assert "reached" not in result.variables


def test_lsp_uses_the_same_condition_error():
    pytest.importorskip("pygls")
    from execsql.lsp.diagnostics import diagnostics

    found = diagnostics("-- !x! IF (HAS_ROWZ(t))\n-- !x! ENDIF\n", None)
    assert [d.message for d in found if d.code == "P004"] == [_message("HAS_ROWZ(t)")]


@pytest.mark.parametrize(
    "condition",
    ["TRUE", "NOTTRUE", "TRUE ANDFALSE", "HAS_ROWS(t)", "EQUALS(a, a)", 'CONTAINS("(", "(")'],
)
def test_existing_valid_syntax_still_parses(condition):
    CondParser(condition, CONDITIONAL_TABLE).parse()


def test_lint_still_accepts_conditions_that_depend_on_variables():
    source = "-- !x! IF (!!condition!!)\n-- !x! ENDIF\n-- !x! ASSERT IS_GT(!!a!!, !!b!!)\n"
    assert not [i for i in lint_source(source, "test.sql") if i.code == "P004"]


def test_custom_registered_tests_are_not_called_unknown_or_evaluated():
    from execsql.script.engine import MetaCommandList

    def unexpected(**kwargs):
        pytest.fail("diagnostics evaluated a condition")

    table = MetaCommandList()
    table.add(r"^(?:CUSTOM\(\d+\))", unexpected, description="CUSTOM", category="condition")
    with pytest.raises(CondParserError, match="Invalid syntax for CUSTOM"):
        CondParser("CUSTOM(bad)", table).parse()


def test_missing_comma_shows_the_documented_syntax():
    assert "Expected: IS_GT(<value1>, <value2>)" in _message("IS_GT(1 2)")


@pytest.mark.parametrize(
    "prefix",
    ["!!flag!! AND ", '"!!flag!!" AND ', "!{flag}! OR ", "ROW_COUNT_GT(t, !!n!!) AND "],
)
@pytest.mark.parametrize("bad", ["HAS_ROWZ(t)", "IS_GT(!!a!! !!b!!)", "TABLE_EXISTS("])
def test_variables_before_a_real_error_do_not_hide_it_in_lint_or_lsp(prefix, bad):
    source = "-- !x! SUB flag TRUE\n-- !x! ASSERT " + prefix + bad + "\n"
    issues = [i for i in lint_source(source, "test.sql") if i.code == "P004"]
    assert [(i.line, i.message) for i in issues] == [(2, _message(bad))]
    pytest.importorskip("pygls")
    from execsql.lsp.diagnostics import diagnostics

    assert [d.message for d in diagnostics(source, None) if d.code == "P004"] == [_message(bad)]


@pytest.mark.parametrize("prefix", ["NOT", "TRUE AND", "FALSE OR", "TRUE ANDNOT"])
def test_adjacent_operators_do_not_become_part_of_a_known_test_name(prefix):
    assert _message(prefix + "TABLE_EXISTS()") == _message("TABLE_EXISTS()")
    assert _message(prefix + "IS_GT(1 2)") == _message("IS_GT(1 2)")


@pytest.mark.parametrize("prefix", ["TRUE AND", "FALSE OR"])
def test_recovering_an_unknown_name_does_not_cross_an_adjacent_binary_operator(prefix):
    assert _message(prefix + "NO_SUCH_FN(x)") == _message("NO_SUCH_FN(x)")


@pytest.mark.parametrize("prefix", ["NOT", "NOTNOT", "TRUE ANDNOT", "FALSE ORNOT"])
@pytest.mark.parametrize("bad", ["TABLE_EXISTS", "TABLE_EXISTS t)", "IS_GT", "IS_GT 1 2)"])
def test_adjacent_not_does_not_hide_a_missing_call_or_opening_parenthesis(prefix, bad):
    assert _message(prefix + bad) == _message(bad)


@pytest.mark.parametrize("prefix", ["NO", "TRUE", "FALSE"])
def test_a_boolean_literal_prefix_does_not_hide_an_unknown_identifier(prefix):
    name = prefix + "IS_GT"
    assert f"Unknown condition test: {name}" in _message(name + "()")
