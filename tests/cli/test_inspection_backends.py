"""Exercise every inspection scope through real URL connections on live backends."""

import json
import os
from urllib.parse import quote

import pytest
from typer.testing import CliRunner

from execsql import inspect_schema
from execsql.cli import app
from tests.live_db import open_backend


def _url(dbms, db):
    if dbms in ("sqlite", "duckdb"):
        return f"{dbms}:///{quote(str(db.db_name), safe='/')}"
    # Adapters clear passwords after connecting. Use the live-test environment,
    # with the same disposable-server defaults as tests.live_db.
    prefix = {"postgres": "PG", "mysql": "MYSQL", "mariadb": "MARIADB", "sqlserver": "MSSQL"}[dbms]
    password = os.environ.get(f"EXECSQL_{prefix}_PASSWORD", "ExecSql_Test123!" if dbms == "sqlserver" else "execsql")
    host, port = db.server_name, db.port
    if dbms == "sqlserver":
        host, _, port = host.rpartition(",")  # open_backend supplies host,port for SQL Server.
    if ":" in host:
        host = f"[{host}]"
    credentials = f"{quote(db.user, safe='')}:{quote(password, safe='')}"
    url = f"{dbms}://{credentials}@{host}:{port}/{quote(db.db_name, safe='')}"
    return url + ("?trust_server_certificate=yes" if dbms == "sqlserver" else "")


@pytest.mark.parametrize("dbms", ["sqlite", "duckdb", "postgres", "mysql", "mariadb", "sqlserver"])
def test_all_inspection_scopes_with_live_url_connections(dbms, tmp_path):
    db = open_backend(dbms, tmp_path)
    table, view = "cli_inspection_samples", "cli_inspection_view"
    created = []
    try:
        db.execute(f"CREATE TABLE {table}(id INTEGER PRIMARY KEY, payload VARCHAR(40))")
        created.append(("TABLE", table))
        db.execute(f"INSERT INTO {table} VALUES (1, 'private_cli_payload')")
        db.execute(f"CREATE VIEW {view} AS SELECT id FROM {table}")
        created.append(("VIEW", view))
        db.commit()
        metadata = inspect_schema(connection=db, table=table)
        assert metadata["success"], metadata
        namespace = metadata["tables"][0]["schema"]
        url = _url(dbms, db)
        scopes = [["database"], ["schema", namespace], ["table", table, "--schema", namespace]]
        for scope in scopes:
            for output_format in ("text", "json"):
                result = CliRunner().invoke(
                    app,
                    ["inspect", *scope, "--dsn", url, "--no-passwd", "--output-format", output_format],
                    env={"COLUMNS": "60"},
                )
                assert result.exit_code == 0, result.output
                assert result.stderr == ""
                assert "private_cli_payload" not in result.stdout
                if output_format == "json":
                    report = json.loads(result.stdout)
                    assert report["success"] and report["adapter"] == db.type.dbms_id
                    assert any(t["name"] == table for t in report["tables"])
                    if scope[0] == "database":
                        assert report["database"]["name"]
                    else:
                        assert "database" not in report
                    if scope[0] == "schema":
                        assert any(t["name"] == view for t in report["tables"])
                elif scope[0] == "database":
                    assert "Database:" in result.stdout and "Engine:" in result.stdout
                elif scope[0] == "schema":
                    # Catalog-qualified names may wrap within Rich's table cells.
                    # Their exact identity is checked in JSON, independently of width.
                    assert "Object" in result.stdout and "Columns" in result.stdout
                    assert "object(s)" in result.stdout
                else:
                    assert "payload" in result.stdout and "Primary key: id" in result.stdout
    finally:
        try:
            db.rollback()
            for kind, name in reversed(created):
                db.execute(f"DROP {kind} {name}")
                db.commit()
        finally:
            db.close()
