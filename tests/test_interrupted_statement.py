"""An interrupted SQL statement is rolled back like a failed one (#139).

The interrupt is raised right after the statement has run in
Database.execute() and before its commit, where Ctrl-C (or a timeout) can
land; the next commit on the connection stored it.
"""

from __future__ import annotations

import sqlite3
import sys
from unittest.mock import patch

import pytest

from execsql import run
from execsql.db.factory import db_SQLite
from execsql.script.variables import SubVarSet

_set = SubVarSet.add_substitution


class _Interrupt(BaseException):
    """Not a KeyboardInterrupt: a timeout raised from a signal handler."""


def _interrupting(nth=1, exc=KeyboardInterrupt):
    """Raise *exc* the *nth* time Database.execute() has run a statement."""
    seen = []

    def hook(self, name, value):
        if name == "$LAST_ROWCOUNT" and sys._getframe(1).f_code.co_name == "execute":
            seen.append(value)
            if len(seen) == nth:
                raise exc
        return _set(self, name, value)

    return patch.object(SubVarSet, "add_substitution", hook)


@pytest.fixture
def db_file(tmp_path):
    f = tmp_path / "t.db"
    with sqlite3.connect(f) as conn:
        conn.execute("create table t (v text)")
    return f


def _rows(db_file):
    with sqlite3.connect(db_file) as conn:
        return [r[0] for r in conn.execute("select v from t")]


@pytest.mark.parametrize("exc", [KeyboardInterrupt, _Interrupt])
def test_the_callers_next_commit_does_not_store_the_interrupted_statement(db_file, exc):
    conn = db_SQLite(str(db_file))
    with _interrupting(exc=exc), pytest.raises(exc):
        run(sql="insert into t values ('interrupted');\n", connection=conn)
    conn.execute("insert into t values ('the caller''s own');")
    conn.commit()
    conn.close()
    assert _rows(db_file) == ["the caller's own"]


def test_under_autocommit_off_the_interrupt_rolls_back_what_was_held(db_file):
    conn = db_SQLite(str(db_file))
    sql = "-- !x! AUTOCOMMIT OFF\ninsert into t values ('held');\ninsert into t values ('interrupted');\n"
    with _interrupting(nth=2), pytest.raises(KeyboardInterrupt):
        run(sql=sql, connection=conn)
    conn.autocommit_on()
    conn.commit()
    conn.close()
    assert _rows(db_file) == []  # as when a statement fails


def test_a_connection_run_opened_is_rolled_back(db_file):
    with _interrupting(), pytest.raises(KeyboardInterrupt):
        run(sql="insert into t values ('interrupted');\n", dsn=f"sqlite:///{db_file}")
    assert _rows(db_file) == []


# At a BREAKPOINT prompt the run carries on after Ctrl-C, so a later commit
# would store the interrupted statement.


def _paused(tmp_path, script, typed, nth):
    from tests.test_interactive import _paused as paused

    with _interrupting(nth=nth):
        return paused(tmp_path, script, typed)


def test_a_statement_interrupted_at_the_prompt_is_not_stored(tmp_path):
    script = "create table t (n integer);\n-- !x! breakpoint\ninsert into t values (2);\n"
    # Database.execute() runs: the create table, the typed insert (interrupted).
    result, out, _, rows = _paused(tmp_path, script, ["insert into t values (1);", ".c"], nth=2)
    assert "(interrupted)" in out
    assert result.success
    assert rows == [2]


def test_a_statement_interrupted_at_the_prompt_inside_a_batch_fails_the_batch(tmp_path):
    script = (
        "create table t (n integer);\n-- !x! begin batch\ninsert into t values (1);\n"
        "-- !x! breakpoint\ninsert into t values (2);\n-- !x! end batch\n"
    )
    # Database.execute() runs: create table, insert 1, the typed insert (interrupted).
    result, _, _, rows = _paused(tmp_path, script, ["insert into t values (9);", ".c"], nth=3)
    assert not result.success
    assert "The batch was not committed: an error on line 1 of <breakpoint>." in result.errors[-1].message
    assert rows == []


def test_the_prompt_reports_the_interrupt_through_sql_error(tmp_path):
    out = tmp_path / "out.txt"
    script = (
        "create table t (n integer);\n-- !x! breakpoint\n"
        f'-- !x! IF (SQL_ERROR()) {{ WRITE "!!$LAST_ERROR!!: !!$ERROR_MESSAGE!!" TO {out} }}\n'
    )
    _paused(tmp_path, script, ["insert into t values (1);", ".c"], nth=2)
    assert out.read_text().splitlines() == ["insert into t values (1);: Interrupted."]


# A metacommand that writes is interrupted the same way: EXECUTE runs a
# procedure that writes, and the interrupt lands before EXECUTE commits.


def _execute_writes_then_is_interrupted():
    from execsql.db.sqlite import SQLiteDatabase

    def exec_cmd(self, querycommand):
        self.conn.execute("insert into t values ('from EXECUTE')")
        raise KeyboardInterrupt

    return patch.object(SQLiteDatabase, "exec_cmd", exec_cmd)


def test_the_callers_next_commit_does_not_store_an_interrupted_metacommands_writes(db_file):
    conn = db_SQLite(str(db_file))
    with _execute_writes_then_is_interrupted(), pytest.raises(KeyboardInterrupt):
        run(sql="-- !x! EXECUTE some_procedure\n", connection=conn)
    conn.execute("insert into t values ('the caller''s own');")
    conn.commit()
    conn.close()
    assert _rows(db_file) == ["the caller's own"]


def test_under_autocommit_off_an_interrupted_metacommands_writes_stay_with_the_script(db_file):
    conn = db_SQLite(str(db_file))
    sql = "-- !x! AUTOCOMMIT OFF\ninsert into t values ('held');\n-- !x! EXECUTE some_procedure\n"
    with _execute_writes_then_is_interrupted(), pytest.raises(KeyboardInterrupt):
        run(sql=sql, connection=conn)
    conn.rollback()  # what the docs tell a caller to do after an interrupt
    conn.close()
    assert _rows(db_file) == []


# execsql's own control flow is not an interrupt: BREAK (a BaseException) and
# HALT (SystemExit) pass through untouched.


def test_break_typed_at_the_prompt_inside_a_batch_is_not_an_interrupt(tmp_path):
    from tests.test_interactive import _paused as paused

    script = (
        "create table t (n integer);\n-- !x! begin batch\ninsert into t values (1);\n"
        "-- !x! sub i 0\n-- !x! loop while (is_gt(1, !!i!!))\n-- !x! sub_add i 1\n-- !x! breakpoint\n-- !x! end loop\n"
        "insert into t values (2);\n-- !x! end batch\n"
    )
    result, _, _, rows = paused(tmp_path, script, ["-- !x! break"])
    assert result.success
    assert rows == [1, 2]
    assert result.variables.get("ERROR_MESSAGE", "") == ""


def test_halt_is_not_an_interrupt(db_file):
    conn = db_SQLite(str(db_file))
    conn.execute("insert into t values ('the caller''s own');")  # not committed yet
    result = run(sql="-- !x! HALT\n", connection=conn)
    assert not result.success
    assert result.variables.get("ERROR_MESSAGE", "") == ""
    conn.commit()
    conn.close()
    assert _rows(db_file) == ["the caller's own"]


def test_a_plain_system_exit_is_an_interrupt(db_file):
    """A SystemExit execsql did not raise to end the run -- its own SIGTERM
    handler's, or a host program's signal handler's -- is an interrupt."""
    conn = db_SQLite(str(db_file))
    with _interrupting(exc=SystemExit(143)):
        result = run(sql="insert into t values ('interrupted');\n", connection=conn)
    assert not result.success
    conn.execute("insert into t values ('the caller''s own');")
    conn.commit()
    conn.close()
    assert _rows(db_file) == ["the caller's own"]


def test_duckdb_rolls_back_a_transaction_begun_partway_through_a_statement(tmp_path):
    pytest.importorskip("duckdb")
    from execsql.db.factory import db_DuckDB

    db = db_DuckDB(str(tmp_path / "t.duckdb"), new_db=True)
    try:
        db.execute("create table t (v integer)")
        db.commit()
        db.execute("insert into t values (1); begin transaction; insert into t values (2);")
        db.rollback()
        assert db.execute("select v from t order by v", fetch=True)[1] == [(1,)]
    finally:
        db.close()


def test_duckdb_rollback_outside_a_transaction_is_not_logged_as_failed(tmp_path):
    pytest.importorskip("duckdb")
    from unittest.mock import MagicMock

    import execsql.state as _state
    from execsql.db.factory import db_DuckDB

    db = db_DuckDB(str(tmp_path / "t.duckdb"), new_db=True)
    _state.exec_log = MagicMock()
    try:
        db.rollback()
    finally:
        db.close()
    _state.exec_log.log_status_info.assert_not_called()
