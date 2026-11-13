"""Human-readable inspection and explicit JSON share the catalog contract."""

import json
import sqlite3

import pytest
from typer.testing import CliRunner

from execsql import inspect_schema
from execsql.cli import app


@pytest.mark.parametrize("flag", ["--dsn", "--connection-string"])
@pytest.mark.parametrize(
    "scope",
    [
        ["database", "--schema", "main", "--table", "samples%"],
        ["table", "samples%", "--schema", "main"],
    ],
)
def test_cli_matches_python_and_reads_no_rows(tmp_path, flag, scope):
    path = tmp_path / "project.sqlite"
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE "samples%" (id INTEGER PRIMARY KEY, location_id INT)')
        db.execute('INSERT INTO "samples%" VALUES (1, 55)')
    dsn = f"sqlite:///{path}"
    result = CliRunner().invoke(
        app,
        ["inspect", *scope, flag, dsn, "--output-format", "json"],
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


@pytest.mark.parametrize("command", ["database", "schema", "table"])
def test_cli_help(command):
    result = CliRunner().invoke(app, ["inspect", command, "--help"])
    assert result.exit_code == 0
    assert "--dsn" in result.stdout and "--connection-string" in result.stdout
    if command == "database":
        assert "--schema" in result.stdout and "--table" in result.stdout
    else:
        assert "NAME" in result.stdout and "[required]" in result.stdout
        assert "--output-format" in result.stdout and "--prompt-password" in result.stdout


@pytest.mark.parametrize("flag", ["--dsn", "--connection-string"])
def test_schema_summary_and_json_match_existing_filter(tmp_path, flag):
    path = tmp_path / "schema.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript(
            "CREATE TABLE samples(id INTEGER PRIMARY KEY); CREATE VIEW sample_ids AS SELECT id FROM samples;",
        )
    dsn = f"sqlite:///{path}"
    args = ["inspect", "schema", "main", flag, dsn]
    text = CliRunner().invoke(app, args)
    assert text.exit_code == 0, text.output
    assert "main.samples" in text.stdout and "main.sample_ids" in text.stdout
    assert "2 object(s)" in text.stdout and "Primary key" in text.stdout
    assert "execsql inspect table NAME" in text.stdout
    machine = CliRunner().invoke(app, [*args, "--output-format", "json"])
    assert machine.exit_code == 0, machine.output
    assert json.loads(machine.stdout) == inspect_schema(dsn=dsn, schema="main")
    assert machine.stderr == ""
    absent = CliRunner().invoke(app, ["inspect", "schema", "MAIN", flag, dsn])
    assert absent.exit_code == 0 and "No matching tables or views." in absent.stdout


@pytest.mark.parametrize("kind", ["TABLE", "VIEW"])
def test_table_inspection_uses_literal_names_and_shows_details(tmp_path, kind):
    path = tmp_path / "literal.sqlite"
    name = "Odd.Name%_"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE source (id INTEGER PRIMARY KEY, parent_id INT REFERENCES source(id))")
        db.execute(f'CREATE {kind} "{name}" ' + ("(value TEXT)" if kind == "TABLE" else "AS SELECT id FROM source"))
    dsn = f"sqlite:///{path}"
    args = ["inspect", "table", name, "--dsn", dsn, "--schema", "main"]
    text = CliRunner().invoke(app, args)
    assert text.exit_code == 0, text.output
    assert f"main.{name} ({kind.lower()})" in text.stdout
    assert "Nullable" in text.stdout and "Primary key:" in text.stdout
    machine = CliRunner().invoke(app, [*args, "--output-format", "json"])
    assert machine.exit_code == 0, machine.output
    assert json.loads(machine.stdout) == inspect_schema(dsn=dsn, schema="main", table=name)
    assert len(json.loads(machine.stdout)["tables"]) == 1
    keys = CliRunner().invoke(app, ["inspect", "table", "source", "--dsn", dsn])
    assert "Primary key: id" in keys.stdout
    assert "(parent_id) -> main.source (id)" in keys.stdout


@pytest.mark.parametrize("command", ["schema", "table"])
@pytest.mark.parametrize("arguments", [[], ["--dsn", "sqlite:///:memory:"], ["samples"]])
def test_object_inspection_requires_name_and_connection(command, arguments):
    result = CliRunner().invoke(app, ["inspect", command, *arguments])
    assert result.exit_code == 2


@pytest.mark.parametrize("command", ["schema", "table"])
def test_object_inspection_rejects_empty_names_before_connecting(monkeypatch, command):
    def unexpected_connect(*args, **kwargs):
        pytest.fail("Invalid names must be rejected before connection")

    monkeypatch.setattr("execsql.api._connect_from_dsn", unexpected_connect)
    result = CliRunner().invoke(app, ["inspect", command, "", "--dsn", "sqlite:///:memory:"])
    assert result.exit_code == 2


def test_inspection_group_lists_all_scopes():
    result = CliRunner().invoke(app, ["inspect", "--help"])
    assert result.exit_code == 0
    for scope in ("database", "schema", "table"):
        assert scope in result.stdout


@pytest.mark.parametrize("flag", ["--dsn", "--connection-string"])
def test_default_output_is_a_readable_overview_and_selected_table_details(tmp_path, flag):
    path = tmp_path / "demo.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE locations(id INTEGER PRIMARY KEY);
        CREATE TABLE samples(id INTEGER PRIMARY KEY, location_id INT REFERENCES locations(id));
        CREATE VIEW sample_ids AS SELECT id FROM samples;
        """)
    args = ["inspect", "database", flag, f"sqlite:///{path}"]
    overview = CliRunner().invoke(app, [*args, "--schema", "main"])
    assert overview.exit_code == 0, overview.output
    assert "Object" in overview.stdout and "Columns" in overview.stdout
    assert "main.samples" in overview.stdout and "main.sample_ids" in overview.stdout
    assert "3 object(s)" in overview.stdout and "execsql inspect table NAME" in overview.stdout
    assert "schema_version" not in overview.stdout
    details = CliRunner().invoke(app, [*args, "--table", "samples"])
    assert details.exit_code == 0, details.output
    assert "main.samples (table)" in details.stdout
    assert "Column" in details.stdout and "Nullable" in details.stdout
    assert "location_id" in details.stdout and "FK" in details.stdout
    assert "Primary key: id" in details.stdout
    assert "(location_id) -> main.locations (id)" in details.stdout
    assert details.stderr == ""


def test_empty_database_shows_main_namespace_with_zero_counts(tmp_path):
    path = tmp_path / "empty.sqlite"
    sqlite3.connect(path).close()
    result = CliRunner().invoke(app, ["inspect", "database", "--dsn", f"sqlite:///{path}"])
    assert result.exit_code == 0
    assert "main" in result.stdout and "Namespace" in result.stdout
    assert "0" in result.stdout


def test_database_overview_and_json_retain_existing_metadata(tmp_path):
    path = tmp_path / "project.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript("CREATE TABLE samples(v INT); CREATE VIEW sample_view AS SELECT v FROM samples;")
    dsn = f"sqlite:///{path}"
    args = ["inspect", "database", "--dsn", dsn]
    text = CliRunner().invoke(app, args)
    assert text.exit_code == 0, text.output
    assert "Database: project.sqlite" in text.stdout and "Engine: SQLite" in text.stdout
    assert "Namespace" in text.stdout and "Tables" in text.stdout and "Views" in text.stdout
    assert "main" in text.stdout and "visible to this connection" in text.stdout
    assert "execsql inspect schema NAME" in text.stdout
    machine = CliRunner().invoke(app, [*args, "--output-format", "json"])
    assert machine.exit_code == 0, machine.output
    result = json.loads(machine.stdout)
    assert result == inspect_schema(dsn=dsn, include_database=True)
    assert result["tables"] == inspect_schema(dsn=dsn)["tables"]
    assert result["schemas"] == [{"name": "main", "table_count": 1, "view_count": 1}]
    for scope in (["database", "--schema", "main"], ["schema", "main"], ["table", "samples"]):
        filtered = CliRunner().invoke(app, ["inspect", *scope, "--dsn", dsn, "--output-format", "json"])
        assert filtered.exit_code == 0, filtered.output
        assert "database" not in json.loads(filtered.stdout)


@pytest.mark.parametrize("kind", ["none", "unknown"])
def test_database_without_namespace_inventory_retains_object_overview(monkeypatch, kind):
    from execsql import schema as discovery

    item = discovery._table(None, "samples", "table")
    metadata = {
        "success": True,
        "dialect": None,
        "adapter": "DSN",
        "tables": [item],
        "database": {"name": "project", "engine": "Driver engine", "namespace_kind": kind},
        "schemas": [] if kind == "none" else None,
    }
    monkeypatch.setattr(discovery, "inspect_schema", lambda **kwargs: metadata)
    result = CliRunner().invoke(app, ["inspect", "database", "--dsn", "unused"])
    assert result.exit_code == 0, result.output
    assert "Database: project" in result.stdout and "Engine: Driver engine" in result.stdout
    assert "samples" in result.stdout and "1 object(s)" in result.stdout
    assert ("Schema enumeration unavailable" in result.stdout) is (kind == "unknown")


def test_namespace_overview_treats_catalog_names_as_literal_text(monkeypatch):
    from execsql import schema as discovery

    metadata = {
        "success": True,
        "dialect": "PostgreSQL",
        "tables": [],
        "database": {"name": "[bold]project\n", "engine": "PostgreSQL", "namespace_kind": "schema"},
        "schemas": [{"name": "[bold]empty\x1b[2J", "table_count": 0, "view_count": 0}],
    }
    monkeypatch.setattr(discovery, "inspect_schema", lambda **kwargs: metadata)
    result = CliRunner().invoke(app, ["inspect", "database", "--dsn", "unused"])
    assert result.exit_code == 0, result.output
    assert "[bold]project\\x0a" in result.stdout and "[bold]empty\\x1b[2J" in result.stdout
    assert "\x1b" not in result.stdout


def test_human_errors_go_to_stderr_with_a_useful_hint(tmp_path):
    result = CliRunner().invoke(app, ["inspect", "database", "--dsn", f"sqlite:///{tmp_path}/missing.db"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Database file does not exist." in result.stderr
    assert "Check the file path" in result.stderr
    assert "never creates" in result.stderr


@pytest.mark.parametrize("namespace", [None, ""])
def test_unavailable_keys_and_unknown_column_metadata_are_explicit(monkeypatch, namespace):
    from execsql import schema as discovery

    item = {
        "catalog": namespace,
        "schema": namespace,
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
    assert "\nsensitive[bold]name (table)\n" in result.stdout  # metadata is never Rich markup
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


@pytest.mark.parametrize("scope", [["database"], ["schema", "main"], ["table", "samples"]])
def test_password_policy_keeps_json_and_redirected_input_noninteractive(monkeypatch, scope):
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
        result = CliRunner().invoke(app, ["inspect", *scope, "--dsn", "postgresql://user@host/db", *options])
        assert result.exit_code == 0, result.output
        assert inspect.call_args.kwargs["prompt_password"] is expected


@pytest.mark.parametrize("scope", [["database"], ["schema", "main"], ["table", "samples"]])
def test_forced_password_prompt_rejects_redirected_input_and_conflicting_flags(scope):
    for options in (["--prompt-password"], ["--prompt-password", "--no-passwd"]):
        result = CliRunner().invoke(app, ["inspect", *scope, "--dsn", "postgresql://user@host/db", *options])
        assert result.exit_code == 2
        assert "terminal" in result.stderr or "cannot be combined" in result.stderr


@pytest.mark.parametrize("scope", [["database"], ["schema", "main"], ["table", "samples"]])
def test_error_output_never_echoes_credentials(monkeypatch, scope):
    def fail(*args, **kwargs):
        raise RuntimeError("password authentication failed: password=not-public postgresql://user:not-public@host/db")

    monkeypatch.setattr("execsql.api._connect_from_dsn", fail)
    args = ["inspect", *scope, "--dsn", "postgresql://user:not-public@host/db"]
    human = CliRunner().invoke(app, args)
    assert human.exit_code == 1
    assert "Database authentication failed." in human.stderr
    assert "--prompt-password" in human.stderr
    assert "not-public" not in human.output
    machine = CliRunner().invoke(app, [*args, "--output-format", "json"])
    assert machine.exit_code == 1
    assert "not-public" not in machine.output
    assert json.loads(machine.stdout)["error"]["code"] == "connection_error"
