"""A data line with trailing values left off is imported with NULLs for them, on every DBMS.

PostgreSQL and MySQL always padded such a line; the other DBMSs stopped the
import ("Too few values" on SQLite, a parameter-count error from DuckDB's
driver), so the same file loaded on one database and not another.  And with
``TO NEW`` the inferred table declared the column NOT NULL on every DBMS,
because type inference skipped the missing values instead of counting them
as NULL.
"""

from __future__ import annotations

import pytest

from execsql import run

pytest.importorskip("duckdb")

CSV = "loc,depth,amt,note\nA,1-2,1.10,x\nC,10-12,3\nD,12-14\n"


def _rows(dsn: str) -> list[tuple]:
    scheme, path = dsn.split(":///", 1)
    if scheme == "duckdb":
        import duckdb

        con = duckdb.connect(path, read_only=True)
    else:
        import sqlite3

        con = sqlite3.connect(path)
    try:
        return con.execute("select loc, cast(amt as varchar), note from t order by loc").fetchall()
    finally:
        con.close()


@pytest.mark.parametrize("scheme", ["duckdb", "sqlite"])
@pytest.mark.parametrize("target", ["NEW t", "t"], ids=["to-new", "existing-table"])
def test_missing_trailing_values_load_as_null(tmp_path, scheme, target):
    csv = tmp_path / "short.csv"
    csv.write_text(CSV)
    dsn = f"{scheme}:///{tmp_path / ('t.' + scheme)}"
    create = (
        ""
        if target.startswith("NEW")
        else "create table t (loc varchar(5), depth varchar(10), amt varchar(10), note varchar(5));\n"
    )
    result = run(sql=f"{create}-- !x! IMPORT TO {target} FROM {csv}\n", dsn=dsn, new_db=True)
    assert result.success, result.errors
    rows = _rows(dsn)
    assert [r[0] for r in rows] == ["A", "C", "D"]
    assert rows[1][2] is None and rows[2][1] is None and rows[2][2] is None


def test_inference_counts_missing_trailing_values_as_null():
    from execsql.models import DataTable

    table = DataTable(["loc", "note"], iter([["A", "x"], ["C"]]))
    assert table.cols[1].column_type()[3] is True  # nullable
