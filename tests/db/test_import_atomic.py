"""A failed IMPORT or COPY leaves nothing behind, on DuckDB as on SQLite and PostgreSQL.

Rows are inserted in batches of ``import_row_buffer`` and committed once at
the end.  psycopg and sqlite3 hold every batch in one transaction, so a
failure rolls them all back.  The DuckDB driver commits each statement unless
a transaction is open, so every batch before the failing one stayed, and a
re-run doubled them.
"""

from __future__ import annotations

import pytest

from execsql import run

pytest.importorskip("duckdb")


def _rows_csv(tmp_path, n=2000):
    path = tmp_path / "p.csv"
    path.write_text("a\n" + "".join(f"{i}\n" for i in range(n)))
    return path


def _count(dsn, table="t"):
    """Row count read with the database's own driver, after execsql has closed it."""
    scheme, path = dsn.split(":///", 1)
    if scheme == "duckdb":
        import duckdb

        con = duckdb.connect(path, read_only=True)
    else:
        import sqlite3

        con = sqlite3.connect(path)
    try:
        return con.execute(f"select count(*) from {table}").fetchone()[0]
    finally:
        con.close()


@pytest.mark.parametrize("scheme", ["duckdb", "sqlite"])
def test_failed_import_leaves_no_rows(tmp_path, scheme):
    dsn = f"{scheme}:///{tmp_path / ('t.' + scheme)}"
    csv = _rows_csv(tmp_path)
    result = run(
        sql=f"create table t (a integer check (a < 1500));\n-- !x! IMPORT TO t FROM {csv}\n",
        dsn=dsn,
        new_db=True,
    )
    assert not result.success
    assert _count(dsn) == 0


@pytest.mark.parametrize("scheme", ["duckdb", "sqlite"])
def test_failed_import_leaves_no_rows_when_the_script_carries_on(tmp_path, scheme):
    """With METACOMMAND_ERROR_HALT OFF the script continues; the partial load must not be committed later."""
    dsn = f"{scheme}:///{tmp_path / ('t.' + scheme)}"
    csv = _rows_csv(tmp_path)
    run(
        sql=(
            "create table t (a integer check (a < 1500));\n"
            "create table after (x integer);\n"
            "-- !x! METACOMMAND_ERROR_HALT OFF\n"
            f"-- !x! IMPORT TO t FROM {csv}\n"
            "insert into after values (1);\n"
        ),
        dsn=dsn,
        new_db=True,
    )
    assert _count(dsn) == 0
    assert _count(dsn, "after") == 1


def test_failed_copy_into_duckdb_leaves_no_rows(tmp_path):
    src = tmp_path / "src.duckdb"
    dsn = f"duckdb:///{tmp_path / 'dst.duckdb'}"
    result = run(
        sql=(
            f"-- !x! CONNECT TO DUCKDB(FILE={src}, NEW) AS src\n"
            "-- !x! USE src\n"
            "create table s as select range as a from range(2000);\n"
            "-- !x! USE initial\n"
            "create table t (a integer check (a < 1500));\n"
            "-- !x! COPY s FROM src TO t IN initial\n"
        ),
        dsn=dsn,
        new_db=True,
    )
    assert not result.success
    assert "CHECK constraint" in result.errors[0].message, result.errors
    assert _count(dsn) == 0


def test_successful_import_is_committed(tmp_path):
    dsn = f"duckdb:///{tmp_path / 't.duckdb'}"
    csv = _rows_csv(tmp_path)
    result = run(sql=f"create table t (a integer);\n-- !x! IMPORT TO t FROM {csv}\n", dsn=dsn, new_db=True)
    assert result.success, result.errors
    assert _count(dsn) == 2000
