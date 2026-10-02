"""A timestamp column mixing values with and without a UTC offset is stored the same on every machine.

Only a column where every value has an offset is ``timestamptz``.  A value
with an offset is not a plain timestamp, so a mixed column is text and keeps
each value as written.  Storing the offset values in a naive ``timestamp``
column let the driver convert them with the client's time zone.
"""

from __future__ import annotations

import os
import time

import pytest

from execsql import run
from execsql.models import DataTable
from execsql.types import DT_Text, DT_TimestampTZ, DT_Varchar

pytest.importorskip("duckdb")

MIXED = ["2024-01-01 10:00+05:00", "2024-01-01 11:00"]


def test_a_mixed_column_is_inferred_as_text():
    table = DataTable(["ts"], iter([[v] for v in MIXED]))
    assert table.cols[0].column_type()[1] in (DT_Varchar, DT_Text)


def test_a_column_where_every_value_has_an_offset_is_timestamptz():
    table = DataTable(["ts"], iter([["2024-01-01 10:00+05:00"], ["2024-01-01 11:00-02:00"]]))
    assert table.cols[0].column_type()[1] is DT_TimestampTZ


@pytest.fixture
def set_tz():
    saved = os.environ.get("TZ")

    def _set(tz: str) -> None:
        os.environ["TZ"] = tz
        time.tzset()

    yield _set
    if saved is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = saved
    time.tzset()


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="time.tzset is POSIX-only")
def test_stored_values_do_not_depend_on_the_client_time_zone(tmp_path, set_tz):
    import duckdb

    csv = tmp_path / "ts.csv"
    csv.write_text("ts\n" + "\n".join(MIXED) + "\n")
    stored = {}
    for tz in ("UTC", "America/Chicago"):
        set_tz(tz)
        db = tmp_path / f"{tz.replace('/', '_')}.duckdb"
        result = run(sql=f"-- !x! IMPORT TO NEW t FROM {csv}\n", dsn=f"duckdb:///{db}", new_db=True)
        assert result.success, result.errors
        con = duckdb.connect(str(db), read_only=True)
        try:
            stored[tz] = con.execute("select cast(ts as varchar) from t order by 1").fetchall()
        finally:
            con.close()
    assert stored["UTC"] == stored["America/Chicago"] == [(v,) for v in sorted(MIXED)]
