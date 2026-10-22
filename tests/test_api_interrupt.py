"""An interrupted run() leaves nothing for the caller's next commit to store (#139).

The interrupt is raised right after the insert has run and before its commit,
where Ctrl-C in a notebook can land.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

from execsql import run
from execsql.db.factory import db_SQLite
from execsql.script.variables import SubVarSet

_set = SubVarSet.add_substitution


def _interrupt_after_the_insert(self, name, value):
    if name == "$LAST_ROWCOUNT" and value is not None:  # set once the insert has run
        raise KeyboardInterrupt
    return _set(self, name, value)


def _interrupted(sql, **kwargs):
    with patch.object(SubVarSet, "add_substitution", _interrupt_after_the_insert), pytest.raises(KeyboardInterrupt):
        run(sql=sql, **kwargs)


@pytest.fixture
def db_file(tmp_path):
    f = tmp_path / "t.db"
    with sqlite3.connect(f) as conn:
        conn.execute("create table t (v text)")
    return f


def _rows(db_file):
    with sqlite3.connect(db_file) as conn:
        return [r[0] for r in conn.execute("select v from t")]


def test_the_interrupted_statement_is_not_stored_by_the_callers_next_commit(db_file):
    conn = db_SQLite(str(db_file))
    _interrupted("insert into t values ('interrupted');\n", connection=conn)
    conn.execute("insert into t values ('the caller''s own');")
    conn.commit()
    conn.close()
    assert _rows(db_file) == ["the caller's own"]


def test_under_autocommit_off_the_held_statements_are_the_callers(db_file):
    conn = db_SQLite(str(db_file))
    _interrupted("-- !x! AUTOCOMMIT OFF\ninsert into t values ('held');\n", connection=conn)
    conn.autocommit_on()
    conn.commit()
    conn.close()
    assert _rows(db_file) == ["held"]


def test_a_connection_run_opened_is_rolled_back_as_it_is_closed(db_file):
    _interrupted("insert into t values ('interrupted');\n", dsn=f"sqlite:///{db_file}")
    assert _rows(db_file) == []
