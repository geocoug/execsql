"""The schema command emits exactly the public API's JSON contract."""

import json
import sqlite3

from typer.testing import CliRunner

from execsql import inspect_schema
from execsql.cli import app


def test_cli_matches_python_and_reads_no_rows(tmp_path):
    path = tmp_path / "project.sqlite"
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE "samples%" (id INTEGER PRIMARY KEY, location_id INT)')
        db.execute('INSERT INTO "samples%" VALUES (1, 55)')
    dsn = f"sqlite:///{path}"
    result = CliRunner().invoke(app, ["list", "schema", "--dsn", dsn, "--schema", "main", "--table", "samples%"])
    assert result.exit_code == 0, result.output
    metadata = json.loads(result.stdout)
    assert metadata == inspect_schema(dsn=dsn, schema="main", table="samples%")
    assert "rows" not in metadata["tables"][0]
    assert result.stderr == ""


def test_cli_error_is_json_and_nonzero(tmp_path):
    result = CliRunner().invoke(app, ["list", "schema", "--dsn", f"sqlite:///{tmp_path}/missing.db"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "connection_error"
    assert result.stderr == ""


def test_cli_help():
    result = CliRunner().invoke(app, ["list", "schema", "--help"])
    assert result.exit_code == 0
    assert "--dsn" in result.stdout and "--schema" in result.stdout and "--table" in result.stdout
