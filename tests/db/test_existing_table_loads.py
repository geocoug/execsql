"""What IMPORT and COPY store in a table that already exists, for every kind of value and column.

Each case is one source column: the values an IMPORT reads from a file
(strings, scanned with string inference) or a COPY reads from a query
(driver values, scanned without it).  It is loaded through
``populate_table`` — as the IMPORT and COPY metacommands load it — into a
column of each type the backend has, and what the column then holds is
compared with ``tests/data/existing_table_loads/<backend>.json``.  The
backends that read a delimited file their own way (PostgreSQL, MySQL) also
IMPORT each text case from a CSV file, by both of their paths, and compare
with ``<backend>_files.json``.

Those files record what execsql stored before the target table's column
types were consulted (issue #100) and before MySQL ran in strict mode
(issue #101).  A difference fails the test unless
``changes.json`` in the same directory lists it, with the value stored
before, the value stored now, and why.  So every change to stored data is
either listed there or caught here.

Set ``EXECSQL_UPDATE_LOAD_GOLDEN=1`` to rewrite a backend's file from the
current code instead of comparing.  Do that only to record the old
behaviour on a backend that has no file yet, from code that predates #100.
"""

from __future__ import annotations

import csv
import datetime
import inspect
import json
import os
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from execsql.db.base import Database
from execsql.exceptions import DataTypeError, ErrInfo
from execsql.importers.csv import importtable
from execsql.models import DataTable
from tests.live_db import open_backend

_DATA = Path(__file__).resolve().parent.parent / "data" / "existing_table_loads"
_UPDATE = os.environ.get("EXECSQL_UPDATE_LOAD_GOLDEN") == "1"

_TZ = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

# IMPORT from a file: every value is a string (or None for a missing value).
_TEXT_CASES: dict[str, list[Any]] = {
    "zero_one": ["1", "0"],
    "yes_no": ["yes", "no"],
    "t_f": ["t", "f"],
    "TRUE_FALSE": ["TRUE", "FALSE"],
    "integers": ["1", "2", "42"],
    "signed_padded": [" 7 ", "+3", "-2"],
    "leading_zeros": ["00701", "02134"],
    "big_integer": ["3000000000"],
    "whole_decimals": ["1.0", "2.0"],
    "fractions": ["1.5", "2.25"],
    "two_places": ["1.50", "2.00"],
    "exponent": ["1e3", "2E2"],
    "small_floats": ["0.1", "1e-20"],
    "iso_dates": ["2024-01-05", "2024-02-06"],
    "dates_and_missing": ["2024-01-05", None],
    "us_dates": ["01/05/2024", "02/06/2024"],
    "day_first_date": ["13/05/2024"],
    "month_names": ["Jan 5, 2024"],
    "timestamps": ["2024-01-05 10:00", "2024-02-06 11:30:15"],
    "timestamps_tz": ["2024-01-05T10:00:00Z", "2024-01-05 10:00:00+05:30"],
    "times": ["10:00", "23:59:59"],
    "words": ["abc", "def"],
    "word_and_number": ["abc", "1"],
    "empty_and_missing": ["", None, "x"],
    "padded_text": ["  pad  "],
    "unicode": ["Ünïcødé"],
    "long_text": ["x" * 300],
}

# COPY from a query: values as the source driver returns them.
_TYPED_CASES: dict[str, list[Any]] = {
    "int_zero_one": [1, 0],
    "ints": [1, 2, 42],
    "bools": [True, False],
    "big_int": [2**40],
    "decimal_whole": [Decimal("1.0"), Decimal("2.0")],
    "decimal_fraction": [Decimal("1.5"), Decimal("2.25")],
    "decimal_scale": [Decimal("1.50")],
    "float_whole": [1.0, 2.0],
    "float_fraction": [1.5, 0.1],
    "date": [datetime.date(2024, 1, 5)],
    "date_and_null": [datetime.date(2024, 1, 5), None],
    "int_and_null": [7, None],
    "datetime": [datetime.datetime(2024, 1, 5, 10, 0)],
    "datetime_tz": [datetime.datetime(2024, 1, 5, 10, 0, tzinfo=_TZ)],
    "time": [datetime.time(10, 0)],
    "text_zero_one": ["1", "0"],
    "text_date": ["2024-01-05"],
    "text_words": ["abc"],
    "bytes": [b"\x00ab"],
}

_COLUMN_TYPES: dict[str, list[str]] = {
    "sqlite": ["text", "integer", "real", "numeric", "boolean", "date"],
    "duckdb": [
        "varchar",
        "integer",
        "bigint",
        "decimal(18,3)",
        "double",
        "boolean",
        "date",
        "timestamp",
        "timestamptz",
        "time",
    ],
    "postgres": [
        "text",
        "varchar(50)",
        "integer",
        "bigint",
        "numeric(18,3)",
        "double precision",
        "boolean",
        "date",
        "timestamp",
        "timestamptz",
        "time",
    ],
    "mysql": [
        "text",
        "varchar(50)",
        "integer",
        "bigint",
        "decimal(18,3)",
        "double",
        "boolean",
        "date",
        "datetime",
        "time",
    ],
    "sqlserver": [
        "varchar(50)",
        "nvarchar(max)",
        "int",
        "bigint",
        "decimal(18,3)",
        "float",
        "bit",
        "date",
        "datetime2",
        "datetimeoffset",
        "time",
    ],
}

_TABLE = "xload_t"

# As IMPORT and COPY call it for a table that was already there.  The code
# that recorded the expected results predates the parameter: it loaded every
# table alike.
_EXISTING = (
    {"existing_table": True} if "existing_table" in inspect.signature(Database.populate_table).parameters else {}
)

# How to read back a column type the driver cannot fetch (pyodbc: "ODBC SQL type -155 is not yet supported").
_READ_AS = {("sqlserver", "datetimeoffset"): "convert(nvarchar(40), v, 121)"}


def _plain(value: Any) -> Any:
    """A fetched value as a stable, JSON-friendly string (``repr`` of a memoryview holds an address)."""
    if isinstance(value, (memoryview, bytearray)):
        value = bytes(value)
    return repr(value)


def _load(db: Any, dbms: str, column_type: str, values: list[Any], infer_strings: bool) -> list[Any] | str:
    """Load *values* into a new ``v`` column of *column_type*; return what it holds, or ``"ERROR"``."""
    tname = db.type.quoted(_TABLE)
    with db._cursor() as curs:
        curs.execute(f"drop table if exists {tname}")
        curs.execute(f"create table {tname} (i integer, v {column_type})")
    db.commit()
    # Row numbers from 100: a lone row numbered 0 or 1 would scan as boolean (#100).
    rows = [[i, v] for i, v in enumerate(values, start=100)]
    try:
        db.populate_table(
            None,
            _TABLE,
            iter(rows),
            ["i", "v"],
            lambda: DataTable(["i", "v"], rows, infer_strings),
            **_EXISTING,
        )
        db.commit()
    except (ErrInfo, DataTypeError):
        db.rollback()
        return "ERROR"
    with db._cursor() as curs:
        curs.execute(f"select {_READ_AS.get((dbms, column_type), 'v')} from {tname} order by i")
        stored = [_plain(r[0]) for r in curs.fetchall()]
        curs.execute(f"drop table {tname}")
    db.commit()
    return stored


def _import_file(db: Any, dbms: str, column_type: str, values: list[Any], path: Path, columns: list[str]) -> Any:
    """IMPORT *values* from a CSV file into a new ``v`` column of *column_type*; return what it holds, or ``"ERROR"``.

    *columns* is the file's header: ``i,v`` matches the table, so MySQL reads
    the file with LOAD DATA; ``v,i`` does not, so it inserts row by row.
    """
    tname = db.type.quoted(_TABLE)
    with db._cursor() as curs:
        curs.execute(f"drop table if exists {tname}")
        curs.execute(f"create table {tname} (i integer, v {column_type})")
    db.commit()
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for i, v in enumerate(values, start=100):
            row = {"i": i, "v": "" if v is None else v}
            writer.writerow([row[c] for c in columns])
    try:
        importtable(db, None, _TABLE, str(path), 0)
    except (ErrInfo, DataTypeError):
        db.rollback()
        return "ERROR"
    with db._cursor() as curs:
        curs.execute(f"select {_READ_AS.get((dbms, column_type), 'v')} from {tname} order by i")
        stored = [_plain(r[0]) for r in curs.fetchall()]
        curs.execute(f"drop table {tname}")
    db.commit()
    return stored


def _scanned(values: list[Any], infer_strings: bool) -> str:
    """The type execsql's scan picks for *values*."""
    return DataTable(["v"], [[v] for v in values], infer_strings).cols[0].column_type()[1].__name__


def _results(db: Any, dbms: str) -> dict[str, Any]:
    stored: dict[str, Any] = {}
    scanned: dict[str, str] = {}
    for source, cases, infer in (("text", _TEXT_CASES, True), ("typed", _TYPED_CASES, False)):
        for case, values in cases.items():
            scanned[f"{source}/{case}"] = _scanned(values, infer)
            for column_type in _COLUMN_TYPES[dbms]:
                stored[f"{source}/{case} -> {column_type}"] = _load(db, dbms, column_type, values, infer)
    return {"scanned": scanned, "stored": stored}


def _file_results(db: Any, dbms: str, tmp_path: Path) -> dict[str, Any]:
    stored: dict[str, Any] = {}
    for path_name, columns in (("load", ["i", "v"]), ("insert", ["v", "i"])):
        for case, values in _TEXT_CASES.items():
            for column_type in _COLUMN_TYPES[dbms]:
                stored[f"file-{path_name}/{case} -> {column_type}"] = _import_file(
                    db,
                    dbms,
                    column_type,
                    values,
                    tmp_path / "load.csv",
                    columns,
                )
    return {"stored": stored}


@pytest.fixture(autouse=True)
def load_settings(minimal_conf):
    """The settings populate_table reads, at their defaults (``ConfigData``)."""
    minimal_conf.import_row_buffer = 1000
    minimal_conf.import_progress_interval = 0
    minimal_conf.show_progress = False
    # IMPORT from a delimited file.
    minimal_conf.import_common_cols_only = False
    minimal_conf.scan_lines = 100
    minimal_conf.import_buffer = 32 * 1024
    minimal_conf.export_row_buffer = 1000


@pytest.fixture
def utc(monkeypatch):
    """Run in UTC, so a value without a zone means the same instant everywhere."""
    monkeypatch.setenv("TZ", "UTC")
    if hasattr(time, "tzset"):
        time.tzset()
    yield
    monkeypatch.undo()
    if hasattr(time, "tzset"):
        time.tzset()


def _session_utc(db: Any, dbms: str) -> None:
    sql = {"duckdb": "set timezone = 'UTC'", "postgres": "set time zone 'UTC'", "mysql": "set time_zone = '+00:00'"}
    if dbms in sql:
        with db._cursor() as curs:
            curs.execute(sql[dbms])
        db.commit()


@pytest.mark.parametrize("dbms", sorted(_COLUMN_TYPES))
def test_existing_table_loads_store_what_they_stored_before(dbms, tmp_path, utc):
    db = open_backend(dbms, tmp_path)
    try:
        _session_utc(db, dbms)
        actual = _results(db, dbms)
    finally:
        db.close()

    _compare_with_record(dbms, actual, _DATA / f"{dbms}.json")


# The backends that read a delimited file their own way instead of through
# populate_table: PostgreSQL (COPY, or inserts of the file's text) and MySQL
# (LOAD DATA, or inserts of the file's text).
_FILE_BACKENDS = ["mysql", "postgres"]


@pytest.mark.parametrize("dbms", _FILE_BACKENDS)
def test_file_imports_into_existing_tables_store_what_they_stored_before(dbms, tmp_path, utc):
    db = open_backend(dbms, tmp_path)
    try:
        _session_utc(db, dbms)
        actual = _file_results(db, dbms, tmp_path)
    finally:
        db.close()
    # IMPORT reports a broken harness (a missing setting) as a load error too.
    assert actual["stored"]["file-load/integers -> integer"] == ["1", "2", "42"], "plain integers did not load"
    _compare_with_record(dbms, actual, _DATA / f"{dbms}_files.json")


def _compare_with_record(dbms: str, actual: dict[str, Any], golden_path: Path) -> None:
    """Fail unless *actual* stores what *golden_path* recorded, apart from the changes listed in changes.json."""
    if _UPDATE:
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(json.dumps(actual, indent=1, ensure_ascii=False, sort_keys=True) + "\n", "utf-8")
        pytest.skip(f"wrote {golden_path.name}")
    if not golden_path.exists():
        pytest.fail(f"no recorded results for {dbms}; record them from code that predates #100")

    before = json.loads(golden_path.read_text("utf-8"))["stored"]
    changes_path = _DATA / "changes.json"
    changes = json.loads(changes_path.read_text("utf-8")).get(dbms, {}) if changes_path.exists() else {}

    assert sorted(actual["stored"]) == sorted(before), "the cases or column types changed; re-record the results"
    unexpected = []
    for key, now in actual["stored"].items():
        if key in changes:
            assert changes[key]["before"] == before[key], f"{key}: changes.json has a stale 'before'"
            expected = changes[key]["after"]
        else:
            expected = before[key]
        if now != expected:
            unexpected.append(f"{key}: expected {expected!r}, stored {now!r}")
    assert not unexpected, f"{len(unexpected)} stored values differ:\n" + "\n".join(unexpected)
