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
    assert "The batch was not committed: an interrupt on line 1 of <breakpoint>." in result.errors[-1].message
    assert rows == []


def test_the_prompt_reports_the_interrupt_through_sql_error(tmp_path):
    out = tmp_path / "out.txt"
    script = (
        "create table t (n integer);\n-- !x! breakpoint\n"
        f'-- !x! IF (SQL_ERROR()) {{ WRITE "!!$LAST_ERROR!!: !!$ERROR_MESSAGE!!" TO {out} }}\n'
    )
    _paused(tmp_path, script, ["insert into t values (1);", ".c"], nth=2)
    assert out.read_text().splitlines() == ["insert into t values (1);: Interrupted."]


def test_end_batch_interrupted_at_the_prompt_fails_the_enclosing_batch(tmp_path):
    from execsql.db.base import Database
    from tests.test_interactive import _paused as paused

    real_commit = Database.commit
    commits = []

    def commit(self):
        commits.append(self)
        if len(commits) == 2:  # the typed END BATCH (the first is the create table)
            self.rollback()  # as Database.commit() does when its commit is interrupted
            raise KeyboardInterrupt
        return real_commit(self)

    script = (
        "create table t (n integer);\n-- !x! begin batch\ninsert into t values (1);\n"
        "-- !x! breakpoint\ninsert into t values (2);\n-- !x! end batch\n"
    )
    typed = ["-- !x! begin batch", "insert into t values (9);", "-- !x! end batch", ".c"]
    with patch.object(Database, "commit", commit):
        result, out, _, rows = paused(tmp_path, script, typed)
    assert "(interrupted)" in out
    assert not result.success
    assert rows == []  # not the outer batch's insert 2 alone


# Ctrl-C at END BATCH before the commit starts (after the last statement, or
# as Database.commit() is entered) left the batch pending on the caller's
# connection, and the caller's next commit stored it.


def _end_batch_interrupted(where):
    from execsql.db.base import Database
    from execsql.script.control import BatchLevels

    if where == "before the commit":

        def failure(self):
            raise KeyboardInterrupt

        return patch.object(BatchLevels, "failure", failure)

    real_commit = Database.commit

    def commit(self):
        if self.autocommit and self.conn.in_transaction:  # END BATCH's, not the create table's
            raise KeyboardInterrupt
        return real_commit(self)

    return patch.object(Database, "commit", commit)


@pytest.mark.parametrize("where", ["before the commit", "entering Database.commit()"])
@pytest.mark.parametrize("nested", [False, True])
def test_end_batch_interrupted_before_its_commit_leaves_nothing_pending(db_file, where, nested):
    conn = db_SQLite(str(db_file))
    batch = "-- !x! begin batch\ninsert into t values ('batched');\n-- !x! end batch\n"
    if nested:
        batch = f"-- !x! begin batch\ninsert into t values ('outer');\n{batch}-- !x! end batch\n"
    with _end_batch_interrupted(where), pytest.raises(KeyboardInterrupt):
        run(sql=batch, connection=conn)
    conn.execute("insert into t values ('the caller''s own');")
    conn.commit()
    conn.close()
    assert _rows(db_file) == ["the caller's own"]


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
    held = [r[0] for r in conn.execute("select v from t order by v", fetch=True)[1]]
    assert held == ["from EXECUTE", "held"]  # not rolled back by execsql
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


def test_quit_typed_at_the_prompt_is_not_an_interrupt(db_file):
    """``.quit`` ends the run on purpose: the caller's own work is left alone."""
    conn = db_SQLite(str(db_file))
    conn.execute("insert into t values ('the caller''s own');")  # not committed yet
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("builtins.input", side_effect=[".quit"]),
        patch("execsql.debug.repl._write"),
        patch("execsql.debug.repl._use_color", return_value=False),
    ):
        result = run(sql="-- !x! breakpoint\n", connection=conn)
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
    assert result.errors[-1].message == "Script interrupted by SystemExit with exit status 143."
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


def test_an_interrupt_is_written_to_the_log():
    from unittest.mock import MagicMock

    from execsql.script.executor import _record_interrupt

    ctx = MagicMock()
    _record_interrupt(ctx, "insert into t values (1);", "s.sql", 3, sql=True)
    ctx.exec_log.log_status_info.assert_called_once_with("SQL statement interrupted on line 3 of s.sql.")


# The prompt catches Ctrl-C and the script carries on: whatever the interrupt
# stopped in the typed input, the open batches must not commit.

_BATCH_AT_PROMPT = (
    "create table t (n integer);\n-- !x! begin batch\ninsert into t values (1);\n"
    "-- !x! breakpoint\ninsert into t values (2);\n-- !x! end batch\n"
)


@pytest.mark.parametrize(
    "typed",
    [
        ['-- !x! if (hasrows(t)) { write "x" }', ".c"],
        [
            "-- !x! begin batch",
            "insert into t values (9);",
            '-- !x! if (hasrows(t)) { write "x" }',
            "-- !x! end batch",
            ".c",
        ],
    ],
    ids=["condition", "condition-in-a-typed-batch"],
)
def test_a_condition_interrupted_at_the_prompt_fails_the_batch(tmp_path, typed):
    from tests.test_interactive import _paused as paused

    with patch("execsql.script.executor.xcmd_test", side_effect=KeyboardInterrupt):
        result, out, _, rows = paused(tmp_path, _BATCH_AT_PROMPT, typed)
    assert "(interrupted)" in out
    assert not result.success
    assert "The batch was not committed: an interrupt in input typed at <breakpoint>." in result.errors[-1].message
    assert rows == []


def test_an_error_typed_at_the_prompt_that_skips_the_error_handling_fails_the_batch(tmp_path):
    """A substitution cycle fails before the statement runs, so no SQL error is
    recorded; the batch still must not commit, and END BATCH says it was an error."""
    from tests.test_interactive import _paused as paused

    typed = ["-- !x! sub a !!b!!", "-- !x! sub b !!a!!", "select '!!a!!';", ".c"]
    result, _, _, rows = paused(tmp_path, _BATCH_AT_PROMPT, typed)
    assert "The batch was not committed: an error in input typed at <breakpoint>." in result.errors[-1].message
    assert rows == []


def test_an_interrupted_metacommand_sets_metacommand_error_at_the_prompt(tmp_path):
    from tests.test_interactive import _paused as paused

    flag = tmp_path / "flag.txt"
    script = "create table t (n integer);\n-- !x! breakpoint\n"
    typed = ["-- !x! EXECUTE some_procedure", f'-- !x! if (metacommand_error()) {{ write "set" to {flag} }}', ".c"]
    with _execute_writes_then_is_interrupted():
        paused(tmp_path, script, typed)
    assert flag.read_text() == "set\n"


def test_an_interrupted_metacommand_rolls_back_a_connection_that_is_not_current(tmp_path):
    """What a metacommand wrote on another connection (COPY to an alias opened
    with CONNECT) must not be stored by that connection's next commit."""
    import execsql.state as _state
    from execsql.db.sqlite import SQLiteDatabase
    from tests.test_interactive import _paused as paused

    other = tmp_path / "other.db"

    def exec_cmd(self, querycommand):
        _state.dbs.aliased_as("other").conn.execute("insert into o values (1)")
        raise KeyboardInterrupt

    script = (
        f"create table t (n integer);\n-- !x! CONNECT TO SQLITE(FILE={other}, NEW) AS other\n"
        "-- !x! use other\ncreate table o (n integer);\n-- !x! use initial\n-- !x! breakpoint\n"
    )
    typed = [
        "-- !x! EXECUTE some_procedure",
        "-- !x! use other",
        "insert into o values (2);",
        "-- !x! use initial",
        ".c",
    ]
    with patch.object(SQLiteDatabase, "exec_cmd", exec_cmd):
        paused(tmp_path, script, typed)
    assert [r[0] for r in sqlite3.connect(other).execute("select n from o order by n")] == [2]


@pytest.mark.parametrize("exc", [SystemExit(), SystemExit("terminated by the supervisor"), SystemExit(True)])
def test_a_system_exit_without_a_number_is_reported_without_a_status(db_file, exc):
    conn = db_SQLite(str(db_file))
    with _interrupting(exc=exc):
        result = run(sql="insert into t values ('interrupted');\n", connection=conn)
    conn.close()
    assert result.errors[-1].message == "Script interrupted by SystemExit."
