"""Python results retain failures before error-halt handlers change runtime state."""

import pytest

from execsql import run
from execsql.db.sqlite import SQLiteDatabase


@pytest.mark.parametrize("halt", ["OFF", "ON"])
def test_handler_errors_follow_original_with_their_own_sql(tmp_path, halt):
    script = tmp_path / "failures.sql"
    script.write_text(
        "-- !x! BEGIN SCRIPT on_error\n"
        f"-- !x! ERROR_HALT {halt}\n"
        "select * from handler_missing;\n"
        "-- !x! END SCRIPT\n"
        "-- !x! ON ERROR_HALT EXECUTE SCRIPT on_error\n"
        "select * from original_missing;\n",
    )
    result = run(script=script, dsn="sqlite:///:memory:")

    assert not result.success
    assert [(e.source, e.line, e.sql) for e in result.errors] == [
        (str(script), 6, "select * from original_missing;"),
        (str(script), 3, "select * from handler_missing;"),
    ]
    assert "original_missing" in result.errors[0].message
    assert "handler_missing" in result.errors[1].message


@pytest.mark.parametrize("handler", ["select 1;", "select * from !!target!!;"])
def test_handler_cannot_replace_expanded_original_sql(handler):
    result = run(
        sql=(
            "-- !x! SUB target original_missing\n"
            "-- !x! ERROR_HALT OFF\n"
            "select * from earlier_missing;\n"
            "-- !x! ERROR_HALT ON\n"
            "-- !x! BEGIN SCRIPT on_error\n"
            "-- !x! SUB target handler_missing\n"
            f"{handler}\n"
            "-- !x! END SCRIPT\n"
            "-- !x! ON ERROR_HALT EXECUTE SCRIPT on_error\n"
            "select * from !!target!!;\n"
        ),
        dsn="sqlite:///:memory:",
    )
    expected = [(3, "select * from earlier_missing;"), (10, "select * from original_missing;")]
    if "!!target!!" in handler:
        expected.append((7, "select * from handler_missing;"))
    assert not result.success
    assert [(e.line, e.sql) for e in result.errors] == expected


@pytest.mark.parametrize("halt", ["OFF", "ON"])
def test_handler_metacommand_error_does_not_reuse_original_sql(halt):
    result = run(
        sql=(
            "-- !x! BEGIN SCRIPT on_error\n"
            f"-- !x! METACOMMAND_ERROR_HALT {halt}\n"
            "-- !x! USE missing_alias\n"
            "-- !x! END SCRIPT\n"
            "-- !x! ON ERROR_HALT EXECUTE SCRIPT on_error\n"
            "select * from original_missing;\n"
        ),
        dsn="sqlite:///:memory:",
    )
    assert not result.success
    assert [(e.line, e.sql) for e in result.errors] == [
        (6, "select * from original_missing;"),
        (3, "USE missing_alias" if halt == "OFF" else None),
    ]
    assert "missing_alias" in result.errors[1].message


@pytest.mark.parametrize("interrupted", [False, True], ids=["halt", "system-exit"])
def test_handler_termination_keeps_original_error(monkeypatch, interrupted):
    if interrupted:
        execute = SQLiteDatabase.execute

        def interrupt_handler(self, sql, *args, **kwargs):
            if sql.strip() == "select 1;":
                raise SystemExit(143)
            return execute(self, sql, *args, **kwargs)

        monkeypatch.setattr(SQLiteDatabase, "execute", interrupt_handler)
    result = run(
        sql=(
            "-- !x! BEGIN SCRIPT on_error\n"
            + ("select 1;\n" if interrupted else "-- !x! HALT\n")
            + "-- !x! END SCRIPT\n"
            "-- !x! ON ERROR_HALT EXECUTE SCRIPT on_error\n"
            "select * from original_missing;\n"
        ),
        dsn="sqlite:///:memory:",
    )
    assert not result.success
    assert len(result.errors) == 2
    assert (result.errors[0].line, result.errors[0].sql) == (5, "select * from original_missing;")
    assert "original_missing" in result.errors[0].message
    assert result.errors[1].line == 2
    assert result.errors[1].sql is None
    assert ("SystemExit" if interrupted else "HALT") in result.errors[1].message
