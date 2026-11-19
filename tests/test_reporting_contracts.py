"""Regression coverage for outcome, counts and structured parser locations."""

import pytest

from execsql import run


@pytest.mark.parametrize("halt", [True, False])
def test_failed_statement_is_an_attempt(halt):
    result = run(sql="select * from missing;", dsn="sqlite:///:memory:", halt_on_error=halt)
    assert result.success is False
    assert result.commands_run == 1
    assert len(result.errors) == 1


def test_zero_status_halt_is_successful():
    result = run(sql="-- !x! HALT EXIT_STATUS 0\nselect * from never_run;", dsn="sqlite:///:memory:")
    assert result.success is True
    assert result.errors == []
    assert result.commands_run == 1


def test_zero_status_halt_does_not_erase_an_earlier_error():
    result = run(
        sql="select * from missing;\n-- !x! HALT EXIT_STATUS 0\n",
        dsn="sqlite:///:memory:",
        halt_on_error=False,
    )
    assert result.success is False
    assert result.commands_run == 2
    assert len(result.errors) == 1
    assert "missing" in result.errors[0].message


@pytest.mark.parametrize(
    "body,line",
    [
        ("select 1;\n-- !x! ENDIF\n", 2),
        ("select 1;\n-- !x! IF (EQUAL(a, a))\nselect 2;\n", 2),
        ("select 1;\n-- !x! LOOP WHILE (EQUAL(a, a))\nselect 2;\n", 2),
        ("select 1;\n-- !x! BEGIN SCRIPT bad(a=1, b)\n-- !x! END SCRIPT\n", 2),
        ("select 1;\nselect 2", 2),
    ],
)
@pytest.mark.parametrize("from_file", [False, True])
def test_parser_locations_are_structured(tmp_path, body, line, from_file):
    script = tmp_path / "bad.sql"
    script.write_text(body)
    result = run(**({"script": script} if from_file else {"sql": body}), dsn="sqlite:///:memory:")
    assert result.success is False
    assert result.commands_run == 0
    assert result.errors[0].source == (str(script) if from_file else "<inline>")
    assert result.errors[0].line == line


@pytest.mark.parametrize("halt", [True, False])
def test_included_parse_error_names_the_included_source(tmp_path, halt):
    child = tmp_path / "bad.sql"
    child.write_text("select 1;\n-- !x! ENDIF\n")
    script = f"-- !x! METACOMMAND_ERROR_HALT {'ON' if halt else 'OFF'}\n-- !x! INCLUDE {child}\n"
    result = run(sql=script, dsn="sqlite:///:memory:")
    assert result.success is False
    assert result.errors[0].source == str(child)
    assert result.errors[0].line == 2
