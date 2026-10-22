"""A statement whose commit fails is rolled back, so no later commit stores it (#135).

The commit fails on SQLite through a deferred foreign key, which is checked at
COMMIT and leaves the transaction open.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from execsql import run
from execsql.db.base import Database

_SETUP = (
    "PRAGMA foreign_keys = ON;\n"
    "create table parent (id integer primary key);\n"
    "create table child (pid integer references parent(id) deferrable initially deferred);\n"
    "create table log (v text);\n"
)


def _run(tmp_path, sql):
    return run(sql=sql, dsn=f"sqlite:///{tmp_path / 'main.db'}", new_db=True)


def _rows(tmp_path, table):
    with sqlite3.connect(tmp_path / "main.db") as conn:
        return [r[0] for r in conn.execute(f"select * from {table}")]


def test_with_error_halt_off_the_next_commit_does_not_store_the_failed_statement(tmp_path):
    sql = (
        "-- !x! ERROR_HALT OFF\n"
        + _SETUP
        + "insert into child values (9);\n"
        + "insert into parent values (9);\n"  # would make the child row valid
    )
    result = _run(tmp_path, sql)
    assert len(result.errors) == 1
    assert "FOREIGN KEY constraint failed" in result.errors[0].message
    assert _rows(tmp_path, "child") == []
    assert _rows(tmp_path, "parent") == [9]


def test_a_second_failed_commit_reports_only_its_own_statement(tmp_path):
    sql = (
        "-- !x! ERROR_HALT OFF\n"
        + _SETUP
        + "insert into child values (9);\n"
        + "insert into log values ('unrelated');\n"
    )
    result = _run(tmp_path, sql)
    assert len(result.errors) == 1  # the log insert is not dragged into the child's failure
    assert _rows(tmp_path, "log") == ["unrelated"]
    assert _rows(tmp_path, "child") == []


def test_the_on_error_halt_script_does_not_commit_the_failed_statement(tmp_path):
    sql = (
        _SETUP
        + "-- !x! BEGIN SCRIPT log_error\ninsert into log values ('logged');\n-- !x! END SCRIPT\n"
        + "-- !x! ON ERROR_HALT EXECUTE SCRIPT log_error\n"
        + "insert into child values (9);\n"
    )
    result = _run(tmp_path, sql)
    assert not result.success
    assert _rows(tmp_path, "log") == ["logged"]
    assert _rows(tmp_path, "child") == []


@pytest.mark.parametrize("exc", [RuntimeError("deferred constraint"), KeyboardInterrupt()])
def test_commit_rolls_back_before_raising(exc):
    db = MagicMock(autocommit=True)
    db.conn.commit.side_effect = exc
    with pytest.raises(type(exc)):
        Database.commit(db)
    db.rollback.assert_called_once_with()


def test_commit_under_autocommit_off_does_nothing():
    db = MagicMock(autocommit=False)
    Database.commit(db)
    db.conn.commit.assert_not_called()
    db.rollback.assert_not_called()
