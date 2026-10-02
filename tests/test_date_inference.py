"""Which date and time shapes ``IMPORT ... TO NEW`` types as dates, times or text.

A value is a date only if it gives a full date with the year written out.
dateutil fills any missing field from today's date, so depth intervals,
ratios, month and weekday names, and year-month values used to become
dates in the current year and lose their text.  Each row here is one column
of an imported file: two values of the same shape.
"""

from __future__ import annotations

import pytest

from execsql.models import Column
from execsql.types import (
    DT_Character,
    DT_Integer,
    DT_Text,
    DT_Time,
    DT_Timestamp,
    DT_TimestampTZ,
    DT_Varchar,
)

#: Any text type: equal-length values infer as fixed-length character.
TEXT = (DT_Character, DT_Varchar, DT_Text)

#: (column, value 1, value 2, inferred type, DuckDB column type)
FORMATS = [
    # Full dates and date-times: still dates.
    ("iso_date", "2024-03-14", "2024-12-01", DT_Timestamp, "TIMESTAMP"),
    ("iso_datetime", "2024-03-14 09:30:00", "2024-12-01 17:05:10", DT_Timestamp, "TIMESTAMP"),
    ("iso_t_micro", "2024-03-14T09:30:00.123456", "2024-12-01T17:05:10.5", DT_Timestamp, "TIMESTAMP"),
    ("iso_z", "2024-03-14T09:30:00Z", "2024-12-01T17:05:10Z", DT_TimestampTZ, "TIMESTAMP WITH TIME ZONE"),
    ("iso_offset", "2024-03-14 09:30-07:00", "2024-12-01 17:05+05:30", DT_TimestampTZ, "TIMESTAMP WITH TIME ZONE"),
    ("ymd_slash", "2024/03/14", "2024/12/01", DT_Timestamp, "TIMESTAMP"),
    ("us_slash", "3/14/2024", "12/1/2024", DT_Timestamp, "TIMESTAMP"),
    ("us_slash_yy", "3/14/24", "12/1/24", DT_Timestamp, "TIMESTAMP"),
    ("us_dash_yy", "03-14-24", "12-01-24", DT_Timestamp, "TIMESTAMP"),
    ("us_ampm", "3/14/2024 9:30 AM", "12/1/2024 5:05 PM", DT_Timestamp, "TIMESTAMP"),
    ("dd_mon_yyyy", "14-Mar-2024", "01-Dec-2024", DT_Timestamp, "TIMESTAMP"),
    ("month_name", "March 14, 2024", "Dec 1, 2024", DT_Timestamp, "TIMESTAMP"),
    ("day_month", "14 March 2024", "1 December 2024", DT_Timestamp, "TIMESTAMP"),
    (
        "rfc2822",
        "Thu, 14 Mar 2024 09:30:00 +0000",
        "Sun, 01 Dec 2024 17:05:10 +0000",
        DT_TimestampTZ,
        "TIMESTAMP WITH TIME ZONE",
    ),
    # Not dates at all, or times without a date.
    ("compact", "20240314", "20241201", DT_Integer, "INTEGER"),
    ("time_only", "09:30", "17:05:10", DT_Time, "TIME"),
    ("time_micro", "09:30:00.123456", "17:05:10.5", DT_Time, "TIME"),
    ("time_ampm", "9:30 AM", "5:05:10 PM", DT_Time, "TIME"),
    # Partial or ambiguous: text.  Each used to be completed from today's date.
    ("time_offset", "09:30:00-07:00", "17:05:10+05:30", TEXT, "VARCHAR"),
    ("depth_ft", "1-2", "10-12", TEXT, "VARCHAR"),
    ("ratio", "5/6", "12/31", TEXT, "VARCHAR"),
    ("month_abbr", "Jan", "Mar", TEXT, "VARCHAR"),
    ("month_day", "March 5", "Dec 1", TEXT, "VARCHAR"),
    ("weekday", "Monday", "Friday", TEXT, "VARCHAR"),
    ("ordinal", "1st", "22nd", TEXT, "VARCHAR"),
    ("year_month", "2024-01", "2024-12", TEXT, "VARCHAR"),
    ("month_year", "Jan 2024", "Dec 2024", TEXT, "VARCHAR"),
    ("day_first_yy", "13-05-24", "31/12/24", TEXT, "VARCHAR"),
    ("dotted", "3.5.7", "4.5.6", TEXT, "VARCHAR"),
]


@pytest.mark.parametrize(("name", "v1", "v2", "expected", "_duck"), FORMATS, ids=[f[0] for f in FORMATS])
def test_column_type_inference(name, v1, v2, expected, _duck):
    col = Column(name)
    col.eval_types(v1)
    col.eval_types(v2)
    inferred = col.column_type()[1]
    assert inferred in expected if isinstance(expected, tuple) else inferred is expected


def test_duckdb_import_keeps_types_and_text(tmp_path):
    """End to end: one file with every shape, imported into DuckDB."""
    duckdb = pytest.importorskip("duckdb")
    import csv

    from execsql import run

    data = tmp_path / "formats.csv"
    with data.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([c[0] for c in FORMATS])
        w.writerow([c[1] for c in FORMATS])
        w.writerow([c[2] for c in FORMATS])
    db = tmp_path / "formats.duckdb"
    result = run(sql=f"-- !x! IMPORT TO NEW formats FROM {data}\n", dsn=f"duckdb:///{db}", new_db=True)
    assert result.success, result.errors

    con = duckdb.connect(str(db), read_only=True)
    try:
        types = dict(
            con.execute(
                "select column_name, data_type from information_schema.columns where table_name = 'formats'",
            ).fetchall(),
        )
        text_cols = [c[0] for c in FORMATS if c[4] == "VARCHAR"]
        stored = con.execute(
            "select " + ", ".join(f'cast("{c}" as varchar)' for c in text_cols) + " from formats",
        ).fetchall()
    finally:
        con.close()

    assert {c[0]: types[c[0]] for c in FORMATS} == {c[0]: c[4] for c in FORMATS}
    expected_text = [tuple(c[i] for c in FORMATS if c[4] == "VARCHAR") for i in (1, 2)]
    assert sorted(stored) == sorted(expected_text)
