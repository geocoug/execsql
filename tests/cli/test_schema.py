"""Human-readable inspection and explicit JSON share the catalog contract."""

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
    result = CliRunner().invoke(
        app,
        ["inspect", "database", "--dsn", dsn, "--schema", "main", "--table", "samples%", "--output-format", "json"],
    )
    assert result.exit_code == 0, result.output
    metadata = json.loads(result.stdout)
    assert metadata == inspect_schema(dsn=dsn, schema="main", table="samples%")
    assert "rows" not in metadata["tables"][0]
    assert result.stderr == ""


def test_cli_error_is_json_and_nonzero(tmp_path):
    result = CliRunner().invoke(
        app,
        ["inspect", "database", "--dsn", f"sqlite:///{tmp_path}/missing.db", "--output-format", "json"],
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "connection_error"
    assert result.stderr == ""


def test_cli_help():
    result = CliRunner().invoke(app, ["inspect", "database", "--help"])
    assert result.exit_code == 0
    assert "--dsn" in result.stdout and "--schema" in result.stdout and "--table" in result.stdout


def test_default_output_is_a_readable_overview_and_selected_table_details(tmp_path):
    path = tmp_path / "demo.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE locations(id INTEGER PRIMARY KEY);
        CREATE TABLE samples(id INTEGER PRIMARY KEY, location_id INT REFERENCES locations(id));
        CREATE VIEW sample_ids AS SELECT id FROM samples;
        """)
    args = ["inspect", "database", "--dsn", f"sqlite:///{path}"]
    overview = CliRunner().invoke(app, args)
    assert overview.exit_code == 0, overview.output
    assert "Object" in overview.stdout and "Columns" in overview.stdout
    assert "main.samples" in overview.stdout and "main.sample_ids" in overview.stdout
    assert "3 object(s)" in overview.stdout and "--table NAME" in overview.stdout
    assert "schema_version" not in overview.stdout
    details = CliRunner().invoke(app, [*args, "--table", "samples"])
    assert details.exit_code == 0, details.output
    assert "main.samples (table)" in details.stdout
    assert "Column" in details.stdout and "Nullable" in details.stdout
    assert "location_id" in details.stdout and "FK" in details.stdout
    assert "Primary key: id" in details.stdout
    assert "(location_id) -> main.locations (id)" in details.stdout
    assert details.stderr == ""


def test_empty_lookup_is_a_successful_human_message(tmp_path):
    path = tmp_path / "empty.sqlite"
    sqlite3.connect(path).close()
    result = CliRunner().invoke(app, ["inspect", "database", "--dsn", f"sqlite:///{path}"])
    assert result.exit_code == 0
    assert "No matching tables or views." in result.stdout


def test_human_errors_go_to_stderr_with_a_useful_hint(tmp_path):
    result = CliRunner().invoke(app, ["inspect", "database", "--dsn", f"sqlite:///{tmp_path}/missing.db"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Database file does not exist." in result.stderr
    assert "Check the file path" in result.stderr
    assert "never creates" in result.stderr


def test_unavailable_keys_and_unknown_column_metadata_are_explicit(monkeypatch):
    from execsql import schema as discovery

    item = {
        "catalog": None,
        "schema": None,
        "name": "sensitive[bold]name",
        "kind": "table",
        "columns": [{"name": "v", "data_type": None, "nullable": None}],
        "primary_key": None,
        "foreign_keys": None,
    }
    metadata = {"success": True, "dialect": None, "adapter": "DSN", "tables": [item]}
    monkeypatch.setattr(discovery, "inspect_schema", lambda **kw: metadata)
    result = CliRunner().invoke(app, ["inspect", "database", "--dsn", "unused", "--table", item["name"]])
    assert result.exit_code == 0, result.output
    assert "DSN (dialect unknown)" in result.stdout
    assert "sensitive[bold]name" in result.stdout  # metadata is never Rich markup
    assert "unknown" in result.stdout and "unavailable" in result.stdout
    assert "Primary key: unavailable" in result.stdout and "Foreign keys: unavailable" in result.stdout


def test_terminal_control_codes_from_catalog_names_are_escaped(monkeypatch):
    from execsql import schema as discovery

    item = {
        "catalog": None,
        "schema": "s",
        "name": "t\x1b[2J\n",
        "kind": "table",
        "columns": [],
        "primary_key": [],
        "foreign_keys": [],
    }
    metadata = {"success": True, "dialect": "SQLite", "tables": [item]}
    monkeypatch.setattr(discovery, "inspect_schema", lambda **kw: metadata)
    result = CliRunner().invoke(app, ["inspect", "database", "--dsn", "unused"])
    assert result.exit_code == 0
    assert "\x1b" not in result.stdout and "\\x1b[2J\\x0a" in result.stdout


def test_password_policy_keeps_json_and_redirected_input_noninteractive(monkeypatch):
    from unittest.mock import MagicMock
    from execsql import schema as discovery

    inspect = MagicMock(return_value={"success": True, "dialect": "SQLite", "tables": []})
    monkeypatch.setattr(discovery, "inspect_schema", inspect)
    for terminal, options, expected in [
        (True, [], True),
        (False, [], False),
        (True, ["--no-passwd"], False),
        (True, ["--output-format", "json"], False),
        (True, ["--output-format", "json", "--prompt-password"], True),
    ]:
        monkeypatch.setattr("execsql.cli.commands.inspect._terminal_available", lambda terminal=terminal: terminal)
        result = CliRunner().invoke(app, ["inspect", "database", "--dsn", "postgresql://user@host/db", *options])
        assert result.exit_code == 0, result.output
        assert inspect.call_args.kwargs["prompt_password"] is expected


def test_forced_password_prompt_rejects_redirected_input_and_conflicting_flags():
    for options in (["--prompt-password"], ["--prompt-password", "--no-passwd"]):
        result = CliRunner().invoke(app, ["inspect", "database", "--dsn", "postgresql://user@host/db", *options])
        assert result.exit_code == 2
        assert "terminal" in result.stderr or "cannot be combined" in result.stderr


def test_error_output_never_echoes_credentials(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("password authentication failed: password=not-public postgresql://user:not-public@host/db")

    monkeypatch.setattr("execsql.api._connect_from_dsn", fail)
    args = ["inspect", "database", "--dsn", "postgresql://user:not-public@host/db"]
    human = CliRunner().invoke(app, args)
    assert human.exit_code == 1
    assert "Database authentication failed." in human.stderr
    assert "--prompt-password" in human.stderr
    assert "not-public" not in human.output
    machine = CliRunner().invoke(app, [*args, "--output-format", "json"])
    assert machine.exit_code == 1
    assert "not-public" not in machine.output
    assert json.loads(machine.stdout)["error"]["code"] == "connection_error"
