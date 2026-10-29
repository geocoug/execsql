"""A commit or a statement that fails in a batch leaves nothing of the batch to commit (#125).

The commit fails on SQLite through a deferred foreign key, which is checked at
COMMIT.  The batch uses the initial database first and ``b`` second, so the
failure comes before ``b`` is committed.
"""

from __future__ import annotations

import sqlite3

import pytest

from execsql import run

_SETUP = (
    "-- !x! CONNECT TO SQLITE(FILE={b}, NEW) AS b\n"
    "-- !x! USE b\ncreate table t (v text);\ncreate table log (v text);\n"
    "-- !x! USE initial\nPRAGMA foreign_keys = ON;\n"
    "create table parent (id integer primary key);\n"
    "create table child (pid integer references parent(id) deferrable initially deferred);\n"
)
_BATCH = (
    "-- !x! BEGIN BATCH\ninsert into child values (99);\n"
    "-- !x! USE b\ninsert into t values ('batch row on b');\n-- !x! USE initial\n"
    "-- !x! END BATCH\n"
)


def _run(tmp_path, sql):
    return run(sql=sql, dsn=f"sqlite:///{tmp_path / 'main.db'}", new_db=True)


def _rows(db, table):
    with sqlite3.connect(db) as conn:
        return [r[0] for r in conn.execute(f"select * from {table}")]


def test_failed_commit_halts_and_rolls_back_the_uncommitted_databases(tmp_path):
    b = tmp_path / "b.db"
    sql = _SETUP.format(b=b) + _BATCH + '-- !x! WRITE "not reached"\n'
    result = _run(tmp_path, sql)
    assert not result.success
    message = result.errors[0].message
    assert "IntegrityError: FOREIGN KEY constraint failed" in message
    assert "Line 14 of script" in message  # the END BATCH line
    assert "Metacommand: END BATCH" in message
    assert _rows(b, "t") == []
    assert _rows(tmp_path / "main.db", "child") == []


def test_on_error_halt_script_does_not_commit_the_failed_batch(tmp_path):
    b = tmp_path / "b.db"
    sql = (
        _SETUP.format(b=b)
        + "-- !x! BEGIN SCRIPT log_error\n-- !x! USE b\ninsert into log values ('logged');\n-- !x! END SCRIPT\n"
        + "-- !x! ON ERROR_HALT EXECUTE SCRIPT log_error\n"
        + _BATCH
    )
    _run(tmp_path, sql)
    assert _rows(b, "t") == []
    assert _rows(b, "log") == ["logged"]


def test_with_error_halt_off_the_script_sees_an_sql_error_and_carries_on(tmp_path):
    b = tmp_path / "b.db"
    out = tmp_path / "out.txt"
    sql = (
        _SETUP.format(b=b)
        + "-- !x! ERROR_HALT OFF\n"
        + _BATCH
        + f'-- !x! IF (SQL_ERROR()) {{ WRITE "failed: !!$LAST_ERROR!!" TO {out} }}\n'
        + "-- !x! USE b\ninsert into t values ('after the batch');\n"
    )
    _run(tmp_path, sql)
    assert out.read_text().splitlines() == ["failed: END BATCH"]
    assert _rows(b, "t") == ["after the batch"]
    assert _rows(tmp_path / "main.db", "child") == []


def test_a_failed_nested_commit_makes_the_enclosing_batch_roll_back(tmp_path):
    b = tmp_path / "b.db"
    out = tmp_path / "out.txt"
    sql = (
        _SETUP.format(b=b)
        + "-- !x! ERROR_HALT OFF\n"
        + "create table o (v text);\n"
        + "-- !x! BEGIN BATCH\ninsert into o values ('outer before');\n"
        + _BATCH
        + f'-- !x! IF (SQL_ERROR()) {{ WRITE "inner failed" TO {out} }}\n'
        + "insert into o values ('outer after inner');\n"
        + "-- !x! END BATCH\n"
        + f'-- !x! IF (SQL_ERROR()) {{ WRITE "outer: !!$ERROR_MESSAGE!!" TO {out} }}\n'
        + "insert into o values ('after both');\n"
    )
    result = _run(tmp_path, sql)
    written = out.read_text()
    assert written.startswith("inner failed\nouter: ")
    assert "The batch was not committed: an error on line 18 of <inline>." in written
    assert _rows(tmp_path / "main.db", "o") == ["after both"]
    assert _rows(tmp_path / "main.db", "child") == []
    assert _rows(b, "t") == []
    assert len(result.errors) == 2


def _nested(tmp_path, middle):
    """An outer batch around the failing batch, then *middle*, then END BATCH."""
    return (
        _SETUP.format(b=tmp_path / "b.db")
        + "-- !x! ERROR_HALT OFF\n"
        + "create table o (v text);\n"
        + "-- !x! BEGIN BATCH\ninsert into o values ('outer before');\n"
        + _BATCH
        + middle
        + "-- !x! END BATCH\n"
        + "insert into o values ('after both');\n"
    )


def test_a_batch_opened_inside_the_failed_batch_does_not_commit_it(tmp_path):
    middle = (
        "insert into o values ('outer after inner');\n"
        "-- !x! BEGIN BATCH\ninsert into o values ('inner2');\n-- !x! END BATCH\n"
        "insert into o values ('outer tail');\n"
    )
    _run(tmp_path, _nested(tmp_path, middle))
    assert _rows(tmp_path / "main.db", "o") == ["after both"]


def test_rollback_batch_does_not_let_the_failed_batch_commit(tmp_path):
    middle = "-- !x! ROLLBACK BATCH\ninsert into o values ('retried');\n"
    result = _run(tmp_path, _nested(tmp_path, middle))
    assert _rows(tmp_path / "main.db", "o") == ["after both"]
    assert len(result.errors) == 2  # the failed commit, then the outer END BATCH


def test_sql_error_right_after_end_batch_is_about_the_batch(tmp_path):
    out = tmp_path / "out.txt"

    def check(label):
        return f'-- !x! IF (SQL_ERROR()) {{ WRITE "{label}: failed" TO {out} }}\n'

    sql = (
        _SETUP.format(b=tmp_path / "b.db")
        + "-- !x! ERROR_HALT OFF\n"
        # The commit fails.
        + "-- !x! BEGIN BATCH\ninsert into child values (99);\n-- !x! END BATCH\n"
        + check("commit failed")
        # A batch with no SQL, after a statement that failed.
        + 'insert into "no such" values (1);\n'
        + "-- !x! BEGIN BATCH\n-- !x! SUB x 1\n-- !x! END BATCH\n"
        + check("no SQL")
    )
    _run(tmp_path, sql)
    assert out.read_text().splitlines() == ["commit failed: failed"]


# Anything that fails inside a batch keeps it from committing: a statement
# (whose failure rolls back its connection, taking the batch's earlier
# statements with it), a metacommand, or SQL a metacommand runs.


def test_a_failed_statement_makes_end_batch_roll_back(tmp_path):
    out = tmp_path / "out.txt"
    sql = (
        "-- !x! ERROR_HALT OFF\ncreate table t (v text);\n"
        "-- !x! BEGIN BATCH\ninsert into t values ('a');\n"
        'insert into "no such" values (1);\n'
        "insert into t values ('b');\n"
        "-- !x! END BATCH\n"
        f'-- !x! IF (SQL_ERROR()) {{ WRITE "!!$LAST_ERROR!!: !!$ERROR_MESSAGE!!" TO {out} }}\n'
        "insert into t values ('after the batch');\n"
    )
    result = _run(tmp_path, sql)
    assert out.read_text().startswith("END BATCH: ")
    assert "The batch was not committed: an error on line 5 of <inline>." in out.read_text()
    assert _rows(tmp_path / "main.db", "t") == ["after the batch"]
    assert len(result.errors) == 2


def test_under_autocommit_off_a_failed_batch_leaves_the_transaction_to_the_script(tmp_path):
    sql = (
        "-- !x! ERROR_HALT OFF\ncreate table t (v text);\n-- !x! AUTOCOMMIT OFF\n"
        '-- !x! BEGIN BATCH\ninsert into "no such" values (1);\n'
        "insert into t values ('kept');\n-- !x! END BATCH\n"
        "COMMIT;\n"
    )
    result = _run(tmp_path, sql)
    assert _rows(tmp_path / "main.db", "t") == ["kept"]
    assert len(result.errors) == 2  # the statement, then END BATCH; COMMIT still commits


# SQL a metacommand runs, and a metacommand that fails without touching the
# database, fail the batch the same way.


@pytest.mark.parametrize(
    "metacommand",
    [
        "EXECUTE nosuch",
        "SUBDATA x nosuch",
        "SELECT_SUB nosuch",
        "EXPORT QUERY <<select * from nosuch;>> TO {out} AS CSV",
    ],
)
def test_sql_a_metacommand_runs_that_fails_makes_end_batch_roll_back(tmp_path, metacommand):
    sql = (
        "-- !x! METACOMMAND_ERROR_HALT OFF\n-- !x! ERROR_HALT OFF\ncreate table t (v text);\n"
        "-- !x! BEGIN BATCH\ninsert into t values ('before');\n"
        f"-- !x! {metacommand.format(out=tmp_path / 'x.csv')}\n"
        "insert into t values ('after');\n"
        "-- !x! END BATCH\n"
    )
    result = _run(tmp_path, sql)
    assert _rows(tmp_path / "main.db", "t") == []
    assert "The batch was not committed: an error on line 6 of <inline>." in result.errors[-1].message


def test_a_metacommand_that_fails_outside_the_database_fails_the_batch(tmp_path):
    sql = (
        "-- !x! METACOMMAND_ERROR_HALT OFF\n-- !x! ERROR_HALT OFF\ncreate table t (v text);\n"
        "-- !x! BEGIN BATCH\ninsert into t values ('a');\n"
        f"-- !x! CD {tmp_path / 'no_such_dir'}\n"
        "insert into t values ('b');\n"
        "-- !x! END BATCH\n"
    )
    result = _run(tmp_path, sql)
    assert _rows(tmp_path / "main.db", "t") == []
    assert "The batch was not committed: an error on line 6 of <inline>." in result.errors[-1].message


def test_an_error_on_a_database_the_batch_has_not_used_fails_it_too(tmp_path):
    b = tmp_path / "b.db"
    sql = (
        "-- !x! METACOMMAND_ERROR_HALT OFF\n-- !x! ERROR_HALT OFF\n"
        f"-- !x! CONNECT TO SQLITE(FILE={b}, NEW) AS b\ncreate table t (v text);\n"
        "-- !x! BEGIN BATCH\ninsert into t values ('a');\n"
        "-- !x! USE b\n-- !x! SUBDATA x nosuch\n-- !x! USE initial\n"
        "-- !x! END BATCH\n"
    )
    result = _run(tmp_path, sql)
    assert _rows(tmp_path / "main.db", "t") == []
    assert len(result.errors) == 2
