"""Create synthetic inspection inputs in a new directory; never overwrite data."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path

STATIONS = [("MW-01", "North well"), ("MW-02", "South well"), ("SW-01", "Creek")]
COLUMNS = ("sample_id", "station_id", "sampled_on", "analyte", "result_mg_l", "detected", "notes")
SAMPLES = [
    ("S001", "MW-01", "2026-11-01", "Nitrate", 1.25, True, "Routine sample"),
    ("S002", "MW-02", "2026-11-01", "Nitrate", None, False, "Below detection limit"),
    ("S003", "SW-01", "2026-11-02", "Nitrate", 0.45, True, "Clear, cool water"),
    ("S004", "MW-01", "2026-11-02", "Chloride", 12.0, True, None),
    ("S005", "MW-02", "2026-11-02", "Chloride", 18.5, True, "Duplicate sample"),
    ("S006", "SW-01", "2026-11-03", "Chloride", None, False, None),
]
STATION_SQL = "CREATE TABLE stations(station_id VARCHAR(12) PRIMARY KEY, station_name VARCHAR(40) NOT NULL)"
SAMPLE_SQL = """CREATE TABLE samples(
    sample_id VARCHAR(12) PRIMARY KEY,
    station_id VARCHAR(12) NOT NULL REFERENCES stations(station_id),
    sampled_on DATE NOT NULL,
    analyte VARCHAR(30) NOT NULL,
    result_mg_l DECIMAL(10,3) CHECK(result_mg_l >= 0),
    detected BOOLEAN NOT NULL DEFAULT FALSE,
    notes VARCHAR(100)
)"""
VIEW_SQL = (
    "CREATE VIEW detected_samples AS SELECT sample_id, station_id, analyte, result_mg_l FROM samples WHERE detected"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="New destination directory (must not already exist).")
    parser.add_argument(
        "--extended",
        action="store_true",
        help="Also create Excel, Parquet, Feather and DuckDB inputs.",
    )
    args = parser.parse_args()
    if args.extended:
        try:
            import duckdb
            import polars as pl
            from openpyxl import Workbook
        except ImportError:
            parser.error(
                "--extended requires the formats and duckdb extras; use uv run --extra formats --extra duckdb.",
            )
    directory = args.directory.expanduser().resolve()
    try:
        directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error("Destination exists; choose a new directory. Existing files are never overwritten.")
    records = [dict(zip(COLUMNS, row)) for row in SAMPLES]
    for filename, delimiter in (("samples.csv", ","), ("samples.tsv", "\t")):
        with (directory / filename).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, delimiter=delimiter)
            writer.writerow(COLUMNS)
            writer.writerows(SAMPLES)
    with (directory / "stations.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("station_id", "station_name"))
        writer.writerows(STATIONS)
    (directory / "samples.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    (directory / "samples.jsonl").write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    with sqlite3.connect(directory / "inspection.sqlite") as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for statement in (STATION_SQL, SAMPLE_SQL, VIEW_SQL):
            connection.execute(statement)
        connection.executemany("INSERT INTO stations VALUES (?,?)", STATIONS)
        connection.executemany("INSERT INTO samples VALUES (?,?,?,?,?,?,?)", SAMPLES)
    if args.extended:
        workbook = Workbook()
        samples = workbook.active
        assert samples is not None
        samples.title = "Samples"
        samples.append(COLUMNS)
        for row in SAMPLES:
            samples.append(row)
        stations = workbook.create_sheet("Stations")
        stations.append(("station_id", "station_name"))
        for station in STATIONS:
            stations.append(station)
        workbook.save(directory / "samples.xlsx")
        workbook.close()
        frame = pl.DataFrame(records).lazy().with_columns(pl.col("sampled_on").str.to_date()).collect()
        frame.write_parquet(directory / "samples.parquet")
        frame.write_ipc(directory / "samples.feather")
        with duckdb.connect(str(directory / "inspection.duckdb")) as connection:
            connection.execute("CREATE SCHEMA lab")
            connection.execute("SET schema='lab'")
            for statement in (STATION_SQL, SAMPLE_SQL, VIEW_SQL):
                connection.execute(statement)
            connection.executemany("INSERT INTO stations VALUES (?,?)", STATIONS)
            connection.executemany("INSERT INTO samples VALUES (?,?,?,?,?,?,?)", SAMPLES)
    print(f"Created inspection examples in {directory}")


if __name__ == "__main__":
    main()
