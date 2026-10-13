"""``!'!var!'!`` stores a value exactly as written, backslashes and apostrophes included."""

from __future__ import annotations

import pytest

from execsql import run

VALUES = [r"C:\data\new", r"x\'; drop table t; --", "O'Brien", "\\", r"two\\backslashes"]


def _script(value: str) -> str:
    return f"-- !x! SUB v {value}\ncreate table t (v text);\ninsert into t values (!'!v!'!);\n"


@pytest.mark.parametrize("value", VALUES)
def test_sqlite_round_trip(tmp_path, value):
    import sqlite3

    db = tmp_path / "t.db"
    result = run(sql=_script(value), dsn=f"sqlite:///{db}", new_db=True)
    assert result.success, result.errors
    con = sqlite3.connect(db)
    try:
        assert con.execute("select v from t").fetchall() == [(value,)]
    finally:
        con.close()


@pytest.mark.parametrize("value", VALUES)
def test_duckdb_round_trip(tmp_path, value):
    duckdb = pytest.importorskip("duckdb")
    db = tmp_path / "t.duckdb"
    result = run(sql=_script(value), dsn=f"duckdb:///{db}", new_db=True)
    assert result.success, result.errors
    con = duckdb.connect(str(db), read_only=True)
    try:
        assert con.execute("select v from t").fetchall() == [(value,)]
    finally:
        con.close()
