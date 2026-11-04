"""ASSERT and WAIT_UNTIL must be able to evaluate their conditions (#117)."""

from __future__ import annotations

import sqlite3

import pytest

from execsql import run
from execsql.db.sqlite import SQLiteDatabase


_COMMANDS = ["ASSERT {condition}", "WAIT_UNTIL {condition} CONTINUE AFTER 2 SECONDS"]


@pytest.mark.parametrize("template", _COMMANDS)
@pytest.mark.parametrize("condition", ["NO_SUCH_FN(x)", "HASROWS(missing)", "IS_GT(not_number, 1)"])
@pytest.mark.parametrize(("sql_halt", "meta_halt"), [(False, False), (True, False), (False, True), (True, True)])
def test_unevaluable_condition_halts_regardless_of_error_settings(tmp_path, template, condition, sql_halt, meta_halt):
    command = template.format(condition=condition)
    sql = (
        f"-- !x! ERROR_HALT {'ON' if sql_halt else 'OFF'}\n"
        f"-- !x! METACOMMAND_ERROR_HALT {'ON' if meta_halt else 'OFF'}\n"
        f"-- !x! {command}\n-- !x! SUB reached_end yes\n"
    )
    result = run(sql=sql, dsn=f"sqlite:///{tmp_path / 't.db'}", new_db=True)
    assert not result.success
    assert "reached_end" not in result.variables
    assert result.errors[0].line == 3
    assert f"Metacommand: {command}" in result.errors[0].message
    assert "Assertion failed" not in result.errors[0].message


@pytest.mark.parametrize("template", _COMMANDS)
@pytest.mark.parametrize("source", ["include", "named-script"])
def test_failure_keeps_the_condition_location(tmp_path, template, source):
    command = template.format(condition="NO_SUCH_FN(x)")
    if source == "include":
        included = tmp_path / "included.sql"
        included.write_text(f"-- !x! {command}\n", encoding="utf-8")
        script = f"-- !x! METACOMMAND_ERROR_HALT OFF\n-- !x! INCLUDE {included}\n"
        line = 1
    else:
        script = (
            "-- !x! METACOMMAND_ERROR_HALT OFF\n-- !x! BEGIN SCRIPT check_condition\n"
            f"-- !x! {command}\n-- !x! END SCRIPT\n-- !x! EXECUTE SCRIPT check_condition\n"
        )
        line = 3
    result = run(sql=script + "-- !x! SUB reached_end yes\n", dsn=f"sqlite:///{tmp_path / 't.db'}", new_db=True)
    assert not result.success
    assert "reached_end" not in result.variables
    assert result.errors[0].line == line
    assert f"Metacommand: {command}" in result.errors[0].message
    if source == "include":
        assert "included.sql" in result.errors[0].source


@pytest.mark.parametrize("template", _COMMANDS)
@pytest.mark.parametrize("condition", ["NO_SUCH_FN(x)", "HASROWS(missing)"])
@pytest.mark.parametrize("nested", [False, True])
def test_bad_condition_abandons_batches_before_the_error_hook(tmp_path, template, condition, nested):
    command = template.format(condition=condition)
    script = (
        "create table t (v text);\ncreate table errors (v text);\n"
        "-- !x! BEGIN SCRIPT log_error\n"
        "insert into errors values (!'!$LAST_ERROR!'!);\n-- !x! END SCRIPT\n"
        "-- !x! ON ERROR_HALT EXECUTE SCRIPT log_error\n"
        "-- !x! ERROR_HALT OFF\n-- !x! METACOMMAND_ERROR_HALT OFF\n"
        "-- !x! BEGIN BATCH\ninsert into t values ('held');\n"
        + ("-- !x! BEGIN BATCH\n" if nested else "")
        + f"-- !x! {command}\ninsert into t values ('after failure');\n-- !x! END BATCH\n"
        + ("-- !x! END BATCH\n" if nested else "")
    )
    result = run(sql=script, dsn=f"sqlite:///{tmp_path / 't.db'}", new_db=True)
    assert not result.success
    with sqlite3.connect(tmp_path / "t.db") as observer:
        assert observer.execute("select v from t").fetchall() == []
        assert observer.execute("select v from errors").fetchall() == [(command,)]


@pytest.mark.parametrize("template", _COMMANDS)
def test_syntax_failure_leaves_autocommit_off_work_to_the_caller(tmp_path, template):
    db = SQLiteDatabase(str(tmp_path / "t.db"))
    db.conn.execute("create table t (v text)")
    command = template.format(condition="NO_SUCH_FN(x)")
    try:
        result = run(
            sql="-- !x! AUTOCOMMIT OFF\n-- !x! METACOMMAND_ERROR_HALT OFF\n"
            "-- !x! BEGIN BATCH\ninsert into t values ('held');\n"
            f"-- !x! {command}\ninsert into t values ('after');\n-- !x! END BATCH\n",
            connection=db,
        )
        assert not result.success
        assert db.conn.execute("select v from t").fetchall() == [("held",)]
        with sqlite3.connect(tmp_path / "t.db") as observer:
            assert observer.execute("select v from t").fetchall() == []
    finally:
        db.conn.close()


def test_wait_until_stops_if_a_later_poll_cannot_evaluate(tmp_path, monkeypatch):
    calls = []

    def evaluate(condition):
        calls.append(condition)
        if len(calls) == 1:
            return False
        raise RuntimeError("poll failed")

    monkeypatch.setattr("execsql.metacommands.control._state.xcmd_test", evaluate)
    monkeypatch.setattr("execsql.metacommands.control.time.sleep", lambda seconds: None)
    result = run(
        sql="-- !x! METACOMMAND_ERROR_HALT OFF\n"
        "-- !x! WAIT_UNTIL FALSE CONTINUE AFTER 2 SECONDS\n-- !x! SUB reached_end yes\n",
        dsn=f"sqlite:///{tmp_path / 't.db'}",
        new_db=True,
    )
    assert not result.success
    assert "reached_end" not in result.variables
    assert "poll failed" in result.errors[0].message
    assert calls == ["FALSE", "FALSE"]


def test_wait_until_sleep_failure_remains_an_ordinary_metacommand_error(tmp_path, monkeypatch):
    def fail(seconds):
        raise RuntimeError("sleep failed")

    monkeypatch.setattr("execsql.metacommands.control.time.sleep", fail)
    result = run(
        sql="-- !x! METACOMMAND_ERROR_HALT OFF\n"
        "-- !x! WAIT_UNTIL FALSE CONTINUE AFTER 1 SECONDS\n-- !x! SUB reached_end yes\n",
        dsn=f"sqlite:///{tmp_path / 't.db'}",
        new_db=True,
    )
    assert not result.success
    assert "sleep failed" in result.errors[0].message
    assert result.variables["reached_end"] == "yes"


def test_false_assertion_still_obeys_metacommand_error_halt(tmp_path):
    result = run(
        sql="-- !x! METACOMMAND_ERROR_HALT OFF\n-- !x! ASSERT FALSE\n-- !x! SUB reached_end yes\n",
        dsn=f"sqlite:///{tmp_path / 't.db'}",
        new_db=True,
    )
    assert not result.success
    assert "**** Assertion failed." in result.errors[0].message
    assert result.variables["reached_end"] == "yes"


@pytest.mark.parametrize("end", ["HALT", "CONTINUE"])
def test_valid_false_wait_condition_keeps_its_timeout_behavior(tmp_path, monkeypatch, end):
    sleeps = []
    monkeypatch.setattr("execsql.metacommands.control.time.sleep", sleeps.append)
    result = run(
        sql="-- !x! METACOMMAND_ERROR_HALT OFF\n"
        f"-- !x! WAIT_UNTIL FALSE {end} AFTER 2 SECONDS\n-- !x! SUB reached_end yes\n",
        dsn=f"sqlite:///{tmp_path / 't.db'}",
        new_db=True,
    )
    assert result.success == (end == "CONTINUE")
    assert ("reached_end" in result.variables) == (end == "CONTINUE")
    assert sleeps == [1, 1]


@pytest.mark.parametrize("template", _COMMANDS)
@pytest.mark.parametrize("condition", ["NO_SUCH_FN(x)", "HASROWS(missing)"])
def test_bad_condition_at_a_breakpoint_fails_the_batch_but_allows_resuming(tmp_path, template, condition):
    from tests.test_interactive import _paused

    script = (
        "create table t (n integer);\n-- !x! ERROR_HALT OFF\n-- !x! METACOMMAND_ERROR_HALT OFF\n"
        "-- !x! BEGIN BATCH\ninsert into t values (1);\n-- !x! BREAKPOINT\n"
        "insert into t values (2);\n-- !x! END BATCH\ninsert into t values (3);\n"
    )
    command = template.format(condition=condition)
    result, output, _, rows = _paused(tmp_path, script, [f"-- !x! {command}", ".c"])
    assert not result.success
    assert ("missing" if condition.startswith("HASROWS") else "_SUCH_FN") in output
    assert rows == [3]


@pytest.mark.parametrize("template", _COMMANDS)
@pytest.mark.parametrize("autocommit", [True, False])
@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_condition_interrupts_keep_the_existing_rollback_rules(tmp_path, monkeypatch, template, autocommit, interrupt):
    def interrupted(condition):
        raise interrupt(143)

    monkeypatch.setattr("execsql.metacommands.control._state.xcmd_test", interrupted)
    db = SQLiteDatabase(str(tmp_path / "t.db"))
    db.conn.execute("create table t (v text)")
    command = template.format(condition="TRUE")
    script = (
        f"-- !x! AUTOCOMMIT {'ON' if autocommit else 'OFF'}\n"
        "-- !x! BEGIN BATCH\ninsert into t values ('held');\n"
        f"-- !x! {command}\ninsert into t values ('after');\n-- !x! END BATCH\n"
    )
    try:
        if interrupt is KeyboardInterrupt:
            with pytest.raises(KeyboardInterrupt):
                run(sql=script, connection=db)
        else:
            result = run(sql=script, connection=db)
            assert not result.success
            assert "Script interrupted by SystemExit" in result.errors[0].message
        assert db.conn.execute("select v from t").fetchall() == ([] if autocommit else [("held",)])
        with sqlite3.connect(tmp_path / "t.db") as observer:
            assert observer.execute("select v from t").fetchall() == []
    finally:
        db.conn.close()
