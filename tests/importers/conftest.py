"""
Real-database fixtures for importer round-trip tests.

The exporter suite proved the point in one direction: a stub database cannot
show what a driver actually returns, and fourteen bugs were hiding in that gap.
The importers have the same gap in the opposite direction — nothing in the
suite has ever written a real file, imported it through a real driver, and
checked what landed in the table.

``import_db`` gives each test a live connection with no tables of its own; the
test writes the file, imports it, and queries the result back.  Backends are
probed once per session, so a machine with no server listening skips instantly
rather than re-dialling for every parametrised test.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

import execsql.state as _state

TABLE_NAME = "import_roundtrip"

#: Every table an importer test may create.  All are dropped before and after
#: each test: PostgreSQL and MySQL keep their server between tests, so a table
#: left behind makes the next `is_new` import fail with "already exists".
TEST_TABLES = (TABLE_NAME, "nl_table")

#: The values every importer test writes to a file and expects back.
#: Each one exists because it is a plausible way for an importer to go wrong:
#: a quote that ends a field early, a delimiter inside a value, a newline that
#: splits a row, an empty field that should be NULL rather than "".
HEADERS = ["id", "n_int", "n_dec", "t_plain", "t_unicode", "t_awkward", "d_date"]

ROWS = [
    [
        1,
        -42,
        Decimal("1234.567"),
        "plain",
        "café — naïve ± 30° ⚡",
        'has "quotes", a comma, and a\nnewline',
        datetime.date(2026, 9, 24),
    ],
    [2, None, None, None, None, None, None],
]


from tests.live_db import BACKEND_NAMES, open_backend


@pytest.fixture(params=BACKEND_NAMES, ids=BACKEND_NAMES)
def import_db(request, tmp_path, minimal_conf):
    """A live Tier 1 connection with the round-trip table dropped and ready."""
    dbms = request.param
    db = open_backend(dbms, tmp_path)

    # minimal_conf covers the pure modules.  The import path and the adapters
    # read a handful more — PostgreSQL's COPY FROM needs a buffer size, and
    # without it the import fails with an AttributeError wrapped in "Can't
    # import from file to table".
    _state.conf.scan_lines = 100
    _state.conf.import_common_cols_only = False
    _state.conf.import_buffer = 32 * 1024
    _state.conf.import_row_buffer = 1000
    _state.conf.export_row_buffer = 1000
    _state.conf.import_progress_interval = 0

    from execsql.db.base import DatabasePool

    pool = DatabasePool()
    pool.add("initial", db)
    _state.dbs = pool

    _drop(db)
    db.dbms_name = dbms  # type: ignore[attr-defined]
    yield db
    _drop(db)
    db.close()


def requires_local_infile(db) -> None:
    """Skip when MySQL's server-side LOAD DATA LOCAL INFILE is switched off.

    The importer's fast path uses it, and MySQL 8 disables it by default. CI
    turns it on; a contributor running a stock container would otherwise see a
    failure that says nothing about execsql.
    """
    if getattr(db, "dbms_name", None) != "mysql":
        return
    try:
        with db._cursor() as curs:
            curs.execute("show global variables like 'local_infile';")
            row = curs.fetchone()
    except Exception:
        return
    if row and str(row[1]).upper() not in ("ON", "1"):
        pytest.skip(
            "MySQL server has local_infile=OFF; start it with --local-infile=1 to exercise the LOAD DATA import path",
        )


def _drop(db) -> None:
    for table in TEST_TABLES:
        try:
            with db._cursor() as curs:
                curs.execute(f"drop table if exists {table};")
            db.commit()
        except Exception:
            pass


def write_csv(path, rows=None, headers=None, delimiter=",") -> str:
    """Write the round-trip values as a real CSV file, quoting as the stdlib does."""
    import csv

    rows = ROWS if rows is None else rows
    headers = HEADERS if headers is None else headers
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=delimiter)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(["" if v is None else str(v) for v in row])
    return str(path)
