"""Database overviews enumerate empty namespaces without reading application rows."""

import json
import sqlite3
from unittest.mock import MagicMock

import pytest

from execsql import inspect_schema
from execsql import schema as discovery
from execsql.db.sqlite import SQLiteDatabase
from tests.live_db import open_backend


def test_attached_namespaces_include_empty_and_count_only_visible_objects():
    db = SQLiteDatabase(":memory:")
    try:
        db.conn.executescript("""
            ATTACH ':memory:' AS "empty's";
            CREATE TABLE samples(value TEXT);
            INSERT INTO samples VALUES ('private-value');
            CREATE VIEW sample_view AS SELECT value FROM samples;
        """)
        reads = []

        def authorize(operation, name, *args):
            if operation == sqlite3.SQLITE_READ:
                reads.append(name)
                if name in ("samples", "sample_view"):
                    return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        db.conn.set_authorizer(authorize)
        result = inspect_schema(connection=db, include_database=True)
        assert result["success"], result
        assert result["database"] == {"name": ":memory:", "engine": "SQLite", "namespace_kind": "attached_database"}
        assert result["schemas"] == [
            {"name": "empty's", "table_count": 0, "view_count": 0},
            {"name": "main", "table_count": 1, "view_count": 1},
        ]
        assert result["capabilities"]["schemas"] is True
        assert not {"samples", "sample_view"} & set(reads)
        assert "private-value" not in json.dumps(result)
    finally:
        db.conn.set_authorizer(None)
        db.close()


@pytest.mark.parametrize("dbms", ["sqlite", "duckdb", "postgres", "mysql", "mariadb", "sqlserver"])
def test_live_identity_and_counts_preserve_existing_table_results(dbms, tmp_path):
    db = open_backend(dbms, tmp_path)
    try:
        original = inspect_schema(connection=db)
        overview = inspect_schema(connection=db, include_database=True)
        assert original["success"] and overview["success"], overview
        assert overview["tables"] == original["tables"]
        assert overview["database"]["name"]
        assert overview["database"]["engine"] == db.type.dbms_id
        assert overview["schema_version"] == original["schema_version"] == 1
        for namespace in overview["schemas"]:
            matching = [t for t in overview["tables"] if t["schema"] == namespace["name"]]
            assert namespace["table_count"] == sum(t["kind"] == "table" for t in matching)
            assert namespace["view_count"] == sum(t["kind"] == "view" for t in matching)
        if dbms in ("mysql", "mariadb"):
            assert overview["database"]["namespace_kind"] == "none"
            assert overview["schemas"] == []
        assert "database" not in original and "schemas" not in original
    finally:
        db.close()


@pytest.mark.parametrize("dbms", ["postgres", "duckdb", "sqlserver"])
def test_live_empty_schema_is_enumerated(dbms, tmp_path):
    db = open_backend(dbms, tmp_path)
    name = "discovery_empty_schema"
    created = False
    try:
        db.execute(f"CREATE SCHEMA {name}")
        db.commit()
        created = True
        result = inspect_schema(connection=db, include_database=True)
        assert result["success"], result
        assert {"name": name, "table_count": 0, "view_count": 0} in result["schemas"]
    finally:
        try:
            db.rollback()
            if created:
                db.execute(f"DROP SCHEMA {name}")
                db.commit()
        finally:
            db.close()


@pytest.mark.parametrize(
    "dialect",
    ["PostgreSQL", "DuckDB", "SQL Server", "Oracle", "MySQL", "Firebird", "Access", "DSN"],
)
def test_catalog_overview_contracts_for_every_adapter(monkeypatch, dialect):
    db = MagicMock()
    db.type.dbms_id = dialect
    db.db_name = "DSN=private;PWD=credential-secret"
    db.paramstr = "%s" if dialect in ("PostgreSQL", "MySQL") else "?"
    cursor = db._cursor.return_value.__enter__.return_value
    cursor.fetchall.side_effect = [[("project", "empty")]] if dialect == "Oracle" else [[("project",)], [("empty",)]]
    db.conn.getinfo.side_effect = lambda code: {16: "project", 17: "Driver Engine", 91: 1}[code]
    cursor.tables.return_value = [(None, "empty", None, None, None)]
    monkeypatch.setitem(discovery._READERS, dialect, lambda *args: [])
    result = inspect_schema(connection=db, include_database=True)
    assert result["success"], result
    assert result["database"]["name"] == "project"
    flat = dialect in ("MySQL", "Firebird", "Access")
    assert result["schemas"] == ([] if flat else [{"name": "empty", "table_count": 0, "view_count": 0}])
    if dialect == "DSN":
        assert result["database"]["engine"] == "Driver Engine"
        cursor.tables.assert_called_once_with(catalog="", schema="%", table="", tableType="")
    assert "credential-secret" not in json.dumps(result)
    db.commit.assert_not_called()
    db.rollback.assert_not_called()
    db.close.assert_not_called()


@pytest.mark.parametrize("usage", [0, None, 1])
def test_odbc_flat_and_unavailable_namespaces_are_distinct(monkeypatch, usage):
    db = MagicMock()
    db.type.dbms_id = "DSN"

    def getinfo(code):
        if code == 91 and usage is None:
            raise RuntimeError("HYC00", "credential-secret")
        return {16: "project", 17: "Engine", 91: usage}[code]

    db.conn.getinfo.side_effect = getinfo
    cursor = db._cursor.return_value.__enter__.return_value
    cursor.tables.side_effect = RuntimeError("IM001", "credential-secret")
    monkeypatch.setitem(discovery._READERS, "DSN", lambda *args: [])
    result = inspect_schema(connection=db, include_database=True)
    assert result["success"], result
    assert result["schemas"] == ([] if usage == 0 else None)
    assert result["database"]["namespace_kind"] == ("none" if usage == 0 else "unknown")
    assert result["capabilities"]["schemas"] is (usage == 0)
    assert "credential-secret" not in json.dumps(result)


def test_odbc_same_schema_across_catalogs_uses_visible_aggregate_counts():
    db = MagicMock()
    db.type.dbms_id = "DSN"
    db.conn.getinfo.side_effect = lambda code: {16: "project", 17: "Engine", 91: 1}[code]
    cursor = db._cursor.return_value.__enter__.return_value
    cursor.tables.return_value = [(None, "public", None, None), (None, "empty", None, None)]
    items = [discovery._table("public", "t", "table"), discovery._table("public", "v", "view")]
    items[0]["catalog"], items[1]["catalog"] = "one", "two"
    identity, namespaces = discovery._database_overview(db, items)
    assert identity["namespace_kind"] == "schema"
    assert namespaces == [
        {"name": "empty", "table_count": 0, "view_count": 0},
        {"name": "public", "table_count": 1, "view_count": 1},
    ]


@pytest.mark.parametrize("failure_at", ["identity", "schemas"])
def test_real_odbc_overview_failures_are_not_reported_as_empty(monkeypatch, failure_at):
    db = MagicMock()
    db.type.dbms_id = "DSN"
    db.conn.getinfo.side_effect = (
        RuntimeError("HY000", "credential-secret")
        if failure_at == "identity"
        else lambda code: {16: "project", 17: "Engine", 91: 1}[code]
    )
    cursor = db._cursor.return_value.__enter__.return_value
    cursor.tables.side_effect = RuntimeError("HY000", "credential-secret")
    monkeypatch.setitem(discovery._READERS, "DSN", lambda *args: [])
    result = inspect_schema(connection=db, include_database=True)
    assert not result["success"]
    assert result["error"]["code"] == "metadata_error"
    assert result["schemas"] is None and result["database"] is None
    assert "credential-secret" not in json.dumps(result)


def test_unsupported_odbc_identity_is_explicit_and_never_uses_connection_string(monkeypatch):
    db = MagicMock()
    db.type.dbms_id = "DSN"
    db.db_name = "DRIVER=Engine;PWD=credential-secret"
    db.conn.getinfo.side_effect = RuntimeError("HY096", "credential-secret")
    monkeypatch.setitem(discovery._READERS, "DSN", lambda *args: [])
    result = inspect_schema(connection=db, include_database=True)
    assert result["success"]
    assert result["database"] == {"name": None, "engine": None, "namespace_kind": "unknown"}
    assert result["schemas"] is None
    assert "credential-secret" not in json.dumps(result)


@pytest.mark.parametrize("failure", [RuntimeError("credential-secret"), KeyboardInterrupt(), SystemExit(143)])
@pytest.mark.parametrize("owned", [True, False])
def test_overview_failure_and_interrupt_preserve_connection_ownership(monkeypatch, failure, owned):
    db = SQLiteDatabase(":memory:")
    db.conn.execute("CREATE TABLE pending(v INT)")
    db.conn.execute("INSERT INTO pending VALUES (7)")
    monkeypatch.setattr("execsql.api._connect_from_dsn", lambda *args, **kwargs: db)
    monkeypatch.setattr(discovery, "_database_overview", MagicMock(side_effect=failure))
    try:
        kwargs = {"dsn": "sqlite:///:memory:"} if owned else {"connection": db}
        if isinstance(failure, RuntimeError):
            result = inspect_schema(**kwargs, include_database=True)
            assert not result["success"] and result["error"]["code"] == "metadata_error"
            assert result["database"] is None and result["schemas"] is None and result["tables"] == []
            assert "credential-secret" not in json.dumps(result)
        else:
            with pytest.raises(type(failure)):
                inspect_schema(**kwargs, include_database=True)
        if owned:
            assert db.conn is None
        else:
            assert db.conn.in_transaction
            assert db.conn.execute("SELECT * FROM pending").fetchall() == [(7,)]
    finally:
        db.close()


@pytest.mark.parametrize("filters", [{"schema": "public"}, {"table": "t"}])
def test_database_overview_rejects_filters_before_connecting(filters):
    with pytest.raises(ValueError, match="unfiltered"):
        inspect_schema(dsn="unused", include_database=True, **filters)
