"""Copyable inspection SQL keeps source definitions and IMPORT inference intact."""

import json
import sqlite3
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from execsql import inspect_file, inspect_schema
from execsql.cli import app
from execsql.config import ConfigData
from tests.test_file_inspection import make_file


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch):
    monkeypatch.setattr(
        ConfigData,
        "_search_paths",
        classmethod(lambda cls, script_path, config_file, start_dir=None: [str(config_file)] if config_file else []),
    )


@pytest.mark.parametrize("kind", ["csv", "tsv", "text", "json", "jsonl", "xls", "xlsx", "ods", "parquet", "feather"])
def test_file_sql_uses_inference_for_every_reader(tmp_path, kind):
    path = make_file(tmp_path, kind)
    before = path.read_bytes()
    kwargs = {"sheet": "Data"} if kind in ("xls", "xlsx", "ods") else {}
    if kind == "xls":
        kwargs["sheet"] = "1"
    report = inspect_file(path, dialect="sqlite", table_name="samples", **kwargs)
    assert report["success"], report
    assert report["scan"]["complete"]
    with sqlite3.connect(":memory:") as db:
        db.executescript(report["sql"])
        columns = db.execute('PRAGMA table_info("samples")').fetchall()
    assert [column[1] for column in columns] == [column["name"] for column in report["columns"]]
    assert [bool(column[3]) for column in columns] == [column["null_count"] == 0 for column in report["columns"]]
    assert path.read_bytes() == before
    assert "sql" not in inspect_file(path, **kwargs)


def test_file_sql_quotes_identifiers_and_keeps_import_case_folding(tmp_path):
    path = tmp_path / "input.csv"
    path.write_text('SampleID,select,"a""b"\n2,x,y\n')
    report = inspect_file(path, dialect="postgres", table_name="NewTable", schema="TargetSchema")
    assert report["success"], report
    assert 'CREATE TABLE "targetschema"."newtable"' in report["sql"]
    assert '"sampleid"' in report["sql"] and '"select"' in report["sql"] and '"a""b"' in report["sql"]


def test_firebird_file_sql_keeps_import_identifier_folding(tmp_path):
    path = tmp_path / "input.csv"
    path.write_text("SampleID,Label Text\n2,alpha\n")
    report = inspect_file(path, dialect="firebird", table_name="Samples")
    assert report["success"], report
    assert 'CREATE TABLE "SAMPLES"' in report["sql"]
    assert '"SAMPLEID"' in report["sql"] and '"Label Text"' in report["sql"]


@pytest.mark.parametrize("system_zone,expected", [("UTC", "+00:00"), ("GMT", "+00:00"), ("EST", None)])
def test_mysql_system_time_zone_is_not_reinterpreted_on_destination(monkeypatch, system_zone, expected):
    from execsql.ddl import DdlError, table_sql

    db = MagicMock()
    db.type.dbms_id = "MySQL"
    rows = MagicMock(
        side_effect=[
            [("", "utf8mb4_general_ci", "SYSTEM", system_zone)],
            [("samples", "CREATE TABLE samples(id INT)")],
        ],
    )
    monkeypatch.setattr("execsql.schema._rows", rows)
    tables = [{"schema": "test", "name": "samples", "kind": "table"}]
    if expected:
        assert f"SET SESSION time_zone = '{expected}';" in table_sql(db, tables)
    else:
        with pytest.raises(DdlError, match="explicit.*time_zone"):
            table_sql(db, tables)


@pytest.mark.parametrize("destination", [[], ["--dialect", "sqlite"], ["--table-name", "samples"]])
def test_cli_file_sql_requires_destination_before_scanning(tmp_path, monkeypatch, destination):
    scan = MagicMock()
    monkeypatch.setattr("execsql.file_inspection.inspect_file", scan)
    path = tmp_path / "input.csv"
    path.write_text("id\n1\n")
    result = CliRunner().invoke(app, ["inspect", "file", str(path), "--output-format", "sql", *destination])
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "requires both --dialect and --table-name" in result.stderr
    scan.assert_not_called()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"dialect": "sqlite"},
        {"table_name": "samples"},
        {"dialect": "unknown", "table_name": "samples"},
        {"dialect": {}, "table_name": "samples"},
        {"dialect": "access", "table_name": "samples", "schema": "public"},
        {"dialect": "firebird", "table_name": "samples", "schema": "public"},
        {"dialect": "sqlite", "table_name": ""},
        {"dialect": "sqlite", "table_name": "samples", "sample_rows": 1},
    ],
)
def test_invalid_file_sql_arguments_fail_before_reading(kwargs):
    with pytest.raises(ValueError):
        inspect_file("missing.csv", **kwargs)


@pytest.mark.skipif(sqlite3.sqlite_version_info < (3, 37), reason="STRICT tables require SQLite 3.37+")
def test_sqlite_table_sql_preserves_native_definition_and_borrowed_work():
    from execsql.db.sqlite import SQLiteDatabase

    db = SQLiteDatabase(":memory:")
    try:
        db.conn.executescript("""CREATE TABLE "sample's" (
            id INTEGER PRIMARY KEY, value TEXT NOT NULL DEFAULT 'a;b',
            doubled TEXT GENERATED ALWAYS AS (value || value), CHECK(length(value)>0)
        ) STRICT; CREATE VIEW broken AS SELECT * FROM absent;""")
        db.conn.execute('INSERT INTO "sample\'s"(id) VALUES (1)')
        report = inspect_schema(connection=db, table="sample's", include_sql=True, include_details=False)
        assert report["success"], report
        assert db.conn.in_transaction
        with sqlite3.connect(":memory:") as target:
            target.executescript(report["sql"])
            target.execute('INSERT INTO "sample\'s"(id) VALUES (2)')
            assert target.execute('SELECT value, doubled FROM "sample\'s"').fetchone() == ("a;b", "a;b" * 2)
        view = inspect_schema(connection=db, table="broken", include_sql=True, include_details=False)
        assert view["success"] and "CREATE VIEW broken" in view["sql"]
        assert db.conn.in_transaction
    finally:
        db.close()


def test_cli_sql_is_sql_only_and_other_scopes_do_not_advertise_it(tmp_path):
    path = tmp_path / "input.csv"
    path.write_text("id,label\n2,alpha\n")
    result = CliRunner().invoke(
        app,
        [
            "inspect",
            "file",
            str(path),
            "--output-format",
            "sql",
            "--dialect",
            "sqlite",
            "--table-name",
            "samples",
        ],
    )
    assert result.exit_code == 0, result.output
    assert result.stderr == "" and result.stdout.startswith("CREATE TABLE ")
    with sqlite3.connect(":memory:") as db:
        db.executescript(result.stdout)
    for scope in (["database"], ["schema", "main"]):
        bad = CliRunner().invoke(app, ["inspect", *scope, "--output-format", "sql"])
        assert bad.exit_code == 2
    machine = CliRunner().invoke(app, ["inspect", "file", str(path), "--output-format", "json"])
    assert "sql" not in json.loads(machine.stdout)


@pytest.mark.parametrize("flag", ["--show-settings", "--show-config", "--sample-rows"])
def test_sql_rejects_presentation_flags_and_samples(tmp_path, flag):
    path = tmp_path / "input.csv"
    path.write_text("id\n2\n")
    args = [
        "inspect",
        "file",
        str(path),
        "--output-format",
        "sql",
        "--dialect",
        "sqlite",
        "--table-name",
        "samples",
        flag,
    ]
    if flag == "--sample-rows":
        args.append("1")
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2 and result.stdout == ""


@pytest.mark.parametrize("dialect", ["sqlite", "duckdb", "postgres", "mysql", "mssql", "oracle", "firebird", "access"])
def test_file_sql_all_target_mappings_without_a_connection(tmp_path, monkeypatch, dialect):
    path = tmp_path / "input.csv"
    path.write_text("id,label,amount\n2,alpha,1.25\n3,,2.50\n")
    connect = MagicMock(side_effect=AssertionError("File SQL must not connect"))
    monkeypatch.setattr("execsql.api._connect_from_dsn", connect)
    report = inspect_file(path, dialect=dialect, table_name="sample's")
    assert report["success"], report
    assert "CREATE TABLE" in report["sql"] and "NOT NULL" in report["sql"]
    assert report["sql"].endswith(";\n")
    connect.assert_not_called()


def test_file_sql_requires_sheet_and_retains_all_null_inference(tmp_path):
    book = make_file(tmp_path, "xlsx")
    missing = inspect_file(book, dialect="sqlite", table_name="samples")
    assert not missing["success"] and missing["sql"] is None
    assert "sheet" in missing["error"]["message"]
    path = tmp_path / "nulls.csv"
    path.write_text("id,label\n2,\n3,\n")
    report = inspect_file(path, dialect="sqlite", table_name="samples")
    assert report["success"], report
    with sqlite3.connect(":memory:") as db:
        db.executescript(report["sql"])
        assert db.execute('PRAGMA table_info("samples")').fetchall()[1][3] == 0


@pytest.mark.parametrize(
    "kwargs",
    [{"include_sql": True}, {"include_sql": True, "table": "samples", "include_database": True}],
)
def test_table_sql_invalid_selection_is_rejected_before_connection(kwargs):
    with pytest.raises(ValueError):
        inspect_schema(dsn="sqlite:///:memory:", **kwargs)


def test_table_sql_cli_preserves_native_comments_and_fails_without_partial_output(tmp_path):
    path = tmp_path / "project.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript("CREATE TABLE samples(id INT); CREATE VIEW sample_view AS SELECT 'a;b' AS label -- comment\n;")
    for name in ("samples", "sample_view"):
        result = CliRunner().invoke(
            app,
            ["inspect", "table", name, "--dsn", f"sqlite:///{path}", "--output-format", "sql"],
        )
        assert result.exit_code == 0, result.output
        assert result.stderr == ""
        with sqlite3.connect(":memory:") as target:
            target.executescript(result.stdout)
    missing = CliRunner().invoke(
        app,
        ["inspect", "table", "missing", "--dsn", f"sqlite:///{path}", "--output-format", "sql"],
    )
    assert missing.exit_code == 1 and missing.stdout == "" and "none was found" in missing.stderr
    for flag in ("--show-config", "--show-settings"):
        invalid = CliRunner().invoke(
            app,
            ["inspect", "table", "samples", "--dsn", f"sqlite:///{path}", "--output-format", "sql", flag],
        )
        assert invalid.exit_code == 2 and invalid.stdout == ""


def test_owned_close_failure_clears_sql(monkeypatch):
    from execsql.db.sqlite import SQLiteDatabase

    db = SQLiteDatabase(":memory:")
    db.conn.execute("CREATE TABLE samples(id INT)")
    original_close = db.close
    monkeypatch.setattr("execsql.api._connect_from_dsn", lambda *args, **kwargs: db)
    monkeypatch.setattr(db, "close", MagicMock(side_effect=RuntimeError("private-secret")))
    try:
        result = inspect_schema(dsn="sqlite:///:memory:", table="samples", include_sql=True, include_details=False)
        assert not result["success"] and result["sql"] is None and result["error"]["code"] == "close_error"
        assert "private-secret" not in json.dumps(result)
    finally:
        original_close()


def test_unsupported_owned_adapter_fails_before_login_or_driver_import(monkeypatch):
    connect = MagicMock(side_effect=AssertionError("Must reject before login"))
    driver = MagicMock(side_effect=AssertionError("Must reject before importing a driver"))
    monkeypatch.setattr("execsql.api._connect_from_dsn", connect)
    monkeypatch.setattr("execsql.schema._check_inspection_driver", driver)
    result = inspect_schema(dsn="oracle://user@host/project", table="samples", include_sql=True)
    assert not result["success"] and result["error"]["code"] == "unsupported_sql" and result["sql"] is None
    connect.assert_not_called()
    driver.assert_not_called()
