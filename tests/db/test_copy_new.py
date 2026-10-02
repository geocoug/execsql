"""``COPY ... TO NEW`` creates the target from the source's values without changing them.

The source rows come from a database cursor, so a text column holds text:
``'1-2'`` stays ``'1-2'`` instead of becoming a timestamp, ``'00123'`` keeps
its zeros, and ``'1'``/``'0'`` are not booleans.  The rows are read once and
spooled to a temporary file while the table is described, so a large COPY
does not hold the whole source in memory.
"""

from __future__ import annotations

import pytest

from execsql import run

pytest.importorskip("duckdb")

# Text columns whose every value looks like another type.
TEXT_COLUMNS = {
    "zip": ["00123", "02134"],
    "flag": ["1", "0"],
    "sampled": ["2024-01-05", "2024-02-06"],
    "amount": ["1.50", "2.25"],
}


def _target(path):
    import duckdb

    con = duckdb.connect(str(path), read_only=True)
    try:
        types = dict(
            con.execute(
                "select column_name, data_type from information_schema.columns where table_name = 't'",
            ).fetchall(),
        )
        rows = con.execute(f"select {', '.join(TEXT_COLUMNS)} from t order by id").fetchall()
        return types, rows
    finally:
        con.close()


@pytest.mark.parametrize(
    "copy",
    [
        "COPY codes FROM src TO NEW t IN dst",
        f"COPY QUERY <<select id, {', '.join(TEXT_COLUMNS)} from codes;>> FROM src TO NEW t IN dst",
    ],
    ids=["copy", "copy-query"],
)
def test_text_values_are_copied_unchanged(tmp_path, copy):
    src, dst = tmp_path / "src.db", tmp_path / "dst.duckdb"
    cols = ", ".join(f"{c} text" for c in TEXT_COLUMNS)
    rows = list(zip(*TEXT_COLUMNS.values()))
    inserts = "".join(
        f"insert into codes values ({i}, {', '.join(repr(v) for v in row)});\n" for i, row in enumerate(rows)
    )
    result = run(
        sql=(
            f"create table codes (id integer, {cols});\n"
            + inserts
            + f"-- !x! CONNECT TO DUCKDB(FILE={dst}, NEW) AS dst\n"
            f"-- !x! CONNECT TO SQLITE(FILE={src}) AS src\n"
            f"-- !x! {copy}\n"
        ),
        dsn=f"sqlite:///{src}",
        new_db=True,
    )
    assert result.success, result.errors
    types, copied = _target(dst)
    assert {c: types[c] for c in TEXT_COLUMNS} == dict.fromkeys(TEXT_COLUMNS, "VARCHAR")
    assert types["id"] != "VARCHAR"
    assert copied == rows


def test_spooled_rows_replay_unchanged_with_bounded_memory():
    import datetime
    import tracemalloc
    from decimal import Decimal

    from execsql.metacommands.io_fileops import _RowSpool

    sample = (1, "text", None, Decimal("1.50"), datetime.datetime(2024, 1, 2, 3, 4), b"\x00\x01")
    spool = _RowSpool(iter([sample, list(sample)]))
    assert list(spool) == [sample, list(sample)]
    assert list(spool.replay()) == [sample, list(sample)]
    spool.close()

    rows = ((i, "x" * 100) for i in range(50_000))
    tracemalloc.start()
    spool = _RowSpool(rows, max_size=1_000_000)
    count = sum(1 for _ in spool)
    replayed = sum(1 for _ in spool.replay())
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    spool.close()
    assert replayed == count == 50_000
    # Holding 50,000 rows of ~150 bytes, on either pass, would take well over 5 MB.
    assert peak < 3_000_000


def test_text_values_copied_into_an_existing_table_are_unchanged(tmp_path):
    """The values are converted by type on the way in, so the types must not come from re-reading the text."""
    src, dst = tmp_path / "src.db", tmp_path / "dst.duckdb"
    cols = ", ".join(f"{c} text" for c in TEXT_COLUMNS)
    rows = list(zip(*TEXT_COLUMNS.values()))
    inserts = "".join(
        f"insert into codes values ({i}, {', '.join(repr(v) for v in row)});\n" for i, row in enumerate(rows)
    )
    result = run(
        sql=(
            f"create table codes (id integer, {cols});\n"
            + inserts
            + f"-- !x! CONNECT TO DUCKDB(FILE={dst}, NEW) AS dst\n"
            f"-- !x! CONNECT TO SQLITE(FILE={src}) AS src\n"
            "-- !x! USE dst\n"
            f"create table t (id integer, {', '.join(f'{c} varchar' for c in TEXT_COLUMNS)});\n"
            "-- !x! USE initial\n"
            "-- !x! COPY codes FROM src TO t IN dst\n"
        ),
        dsn=f"sqlite:///{src}",
        new_db=True,
    )
    assert result.success, result.errors
    assert _target(dst)[1] == rows
