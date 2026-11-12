"""Catalog contracts, ownership and adapter queries; no user rows are fetched."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from execsql import inspect_schema
from execsql import schema as discovery
from execsql.db.sqlite import SQLiteDatabase
from tests.live_db import open_backend


@pytest.mark.parametrize("dbms", ["sqlite", "duckdb", "postgres", "mysql", "mariadb", "sqlserver"])
def test_live_catalog_composite_keys_and_views(dbms, tmp_path):
    db = open_backend(dbms, tmp_path)
    parent, child, view = "discovery_parent", "discovery_child", "discovery_view"
    try:
        db.execute(f"CREATE TABLE {parent} (a INTEGER, b INTEGER, PRIMARY KEY (b, a))")
        db.execute(f"CREATE TABLE {child} (x INTEGER, y INTEGER, FOREIGN KEY (x,y) REFERENCES {parent}(b,a))")
        db.execute(f"CREATE VIEW {view} AS SELECT x, y FROM {child}")
        db.commit()
        result = inspect_schema(connection=db, table=child)
        assert result["success"], result
        assert result["schema_version"] == 1
        assert len(result["tables"]) == 1
        item = result["tables"][0]
        assert item["name"] == child
        assert [c["name"] for c in item["columns"]] == ["x", "y"]
        assert [c["ordinal_position"] for c in item["columns"]] == [1, 2]
        assert all(c["data_type"] for c in item["columns"])
        assert item["primary_key"] == []
        fk = item["foreign_keys"][0]
        assert fk["columns"] == ["x", "y"]
        assert fk["referenced_columns"] == ["b", "a"]
        assert fk["referenced_table"] == parent
        assert inspect_schema(connection=db, table=parent)["tables"][0]["primary_key"] == ["b", "a"]
        assert inspect_schema(connection=db, table=view)["tables"][0]["kind"] == "view"
        assert inspect_schema(connection=db, table="no_discovery_table")["tables"] == []
        assert inspect_schema(connection=db, schema="no_discovery_schema")["tables"] == []
        assert json.loads(json.dumps(result)) == result
    finally:
        db.rollback()
        for kind, name in (("VIEW", view), ("TABLE", child), ("TABLE", parent)):
            try:
                db.execute(f"DROP {kind} {name}")
                db.commit()
            except Exception:
                db.rollback()
        db.close()


@pytest.fixture
def sqlite_db():
    db = SQLiteDatabase(":memory:")
    yield db
    db.close()


def test_sqlite_attached_schemas_quoted_names_generated_columns_and_implicit_fk(sqlite_db):
    db = sqlite_db
    db.conn.executescript("""
    ATTACH ':memory:' AS "other's";
    CREATE TABLE "other's"."parent's" (a INT, b INT, PRIMARY KEY(b,a));
    CREATE TABLE "other's"."child's" (x INT, y INT, z INT AS (x+y),
        FOREIGN KEY(x,y) REFERENCES "parent's");
    CREATE TABLE main."child's" (unrelated TEXT);
    """)
    result = inspect_schema(connection=db, schema="other's", table="child's")
    assert result["success"]
    item = result["tables"][0]
    assert item["schema"] == "other's"
    assert [c["name"] for c in item["columns"]] == ["x", "y", "z"]
    assert item["foreign_keys"][0]["referenced_columns"] == ["b", "a"]
    assert item["foreign_keys"][0]["referenced_schema"] == "other's"
    assert len(inspect_schema(connection=db, table="child's")["tables"]) == 2


@pytest.mark.parametrize("table", ["t%", "t_", "T", "t'; DROP TABLE t;--"])
def test_filters_are_exact_names_not_patterns_or_sql(sqlite_db, table):
    sqlite_db.conn.execute("CREATE TABLE t (v INT)")
    result = inspect_schema(connection=sqlite_db, table=table)
    assert result["success"] and result["tables"] == []
    assert inspect_schema(connection=sqlite_db, table="t")["tables"][0]["name"] == "t"


@pytest.mark.parametrize("autocommit", [True, False])
def test_borrowed_connection_keeps_pending_writes_and_context(sqlite_db, autocommit):
    import execsql.state as state

    original = state.get_context()
    sqlite_db.autocommit = autocommit
    sqlite_db.conn.execute("CREATE TABLE t(v INT)")
    sqlite_db.conn.execute("INSERT INTO t VALUES (17)")
    assert sqlite_db.conn.in_transaction
    assert inspect_schema(connection=sqlite_db)["success"]
    assert state.get_context() is original
    assert sqlite_db.conn.in_transaction
    sqlite_db.conn.rollback()
    assert sqlite_db.conn.execute("SELECT * FROM t").fetchall() == []


def test_failure_does_not_rollback_or_close_borrowed_connection(sqlite_db, monkeypatch):
    sqlite_db.conn.execute("CREATE TABLE t(v INT)")
    sqlite_db.conn.execute("INSERT INTO t VALUES (17)")
    closed = MagicMock()
    monkeypatch.setattr(sqlite_db, "close", closed)
    monkeypatch.setattr(discovery, "_sqlite", MagicMock(side_effect=RuntimeError("password=secret")))
    monkeypatch.setitem(discovery._READERS, "SQLite", discovery._sqlite)
    result = inspect_schema(connection=sqlite_db)
    assert not result["success"] and result["error"]["code"] == "metadata_error"
    assert "secret" not in json.dumps(result)
    assert result["tables"] == []
    assert sqlite_db.conn.in_transaction
    assert sqlite_db.conn.execute("SELECT * FROM t").fetchall() == [(17,)]
    closed.assert_not_called()


@pytest.mark.parametrize("failure", [None, RuntimeError("secret"), KeyboardInterrupt(), SystemExit(143)])
def test_owned_connection_closes_on_success_failure_and_interrupt(sqlite_db, monkeypatch, failure):
    monkeypatch.setattr("execsql.api._connect_from_dsn", lambda *a, **kw: sqlite_db)
    if failure:
        monkeypatch.setitem(discovery._READERS, "SQLite", MagicMock(side_effect=failure))
    if isinstance(failure, (KeyboardInterrupt, SystemExit)):
        with pytest.raises(type(failure)):
            inspect_schema(dsn="sqlite:///file.db")
    else:
        result = inspect_schema(dsn="sqlite:///file.db")
        assert result["success"] == (failure is None)
    assert sqlite_db.conn is None


def test_connection_errors_are_structured_and_secret_free(monkeypatch, capsys):
    def fail(*args, **kwargs):
        assert kwargs["prompt_password"] is False
        raise ValueError("postgresql://user:password@host/db")

    monkeypatch.setattr("execsql.api._connect_from_dsn", fail)
    result = inspect_schema(dsn="postgresql://user:password@host/db")
    assert result["error"]["code"] == "connection_error"
    assert "password" not in json.dumps(result)
    assert capsys.readouterr() == ("", "")


def test_close_failure_is_reported(sqlite_db, monkeypatch):
    monkeypatch.setattr("execsql.api._connect_from_dsn", lambda *a, **kw: sqlite_db)
    with monkeypatch.context() as patch:
        patch.setattr(sqlite_db, "close", MagicMock(side_effect=RuntimeError("secret")))
        result = inspect_schema(dsn="sqlite:///")
    assert not result["success"] and result["tables"] == []
    assert result["error"]["code"] == "close_error"


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"dsn": "x", "connection": object()},
        {"dsn": "x", "schema": ""},
        {"dsn": "x", "table": "a\x00b"},
        {"dsn": "x", "table": 1},
    ],
)
def test_invalid_arguments_raise(kwargs):
    with pytest.raises(ValueError):
        inspect_schema(**kwargs)


def test_missing_database_is_not_created(tmp_path):
    path = tmp_path / "absent.sqlite"
    result = inspect_schema(dsn=f"sqlite:///{path}")
    assert not result["success"] and result["error"]["code"] == "connection_error"
    assert not path.exists()


def test_unsupported_adapter_does_not_issue_queries():
    db = SimpleNamespace(type=SimpleNamespace(dbms_id="plugin"), cursor=MagicMock())
    result = inspect_schema(connection=db)
    assert result["error"]["code"] == "unsupported_adapter"
    db.cursor.assert_not_called()


@pytest.mark.parametrize(
    "dialect",
    ["PostgreSQL", "MySQL", "SQL Server", "DuckDB", "Oracle", "Firebird", "Access", "DSN"],
)
def test_all_adapter_catalog_contracts_and_bound_filters(dialect):
    """Native catalogs not present in CI use realistic DB-API catalog rows."""
    db = MagicMock()
    db.type.dbms_id = dialect
    db.paramstr = "%s" if dialect in ("MySQL", "PostgreSQL") else "?"
    cursor = db._cursor.return_value.__enter__.return_value
    namespace = None if dialect in ("Firebird", "Access", "DSN") else "project"
    name = "sample's"
    if dialect in ("Access", "DSN"):
        db.conn.getinfo.return_value = "\\"
        cursor.tables.return_value = [("catalog", namespace, name, "TABLE")]
        row = [None] * 18
        row[0:4] = ["catalog", namespace, name, "id"]
        row[5], row[10], row[16] = "INTEGER", 0, 1
        cursor.columns.return_value = [row]
        cursor.primaryKeys.side_effect = RuntimeError("IM001", "unsupported")
        cursor.foreignKeys.side_effect = RuntimeError("HYC00", "unsupported")
    elif dialect == "Firebird":
        cursor.fetchall.side_effect = [[(name + "  ", None)], [("id  ", 0, "LONG  ", 1, 0)], [("id  ",)], []]
    else:
        cursor.fetchall.side_effect = [
            [(namespace, name, "BASE TABLE")],
            [("id", 1, "INTEGER", "Y" if dialect == "Oracle" else "NO")],
            [("id",)],
            [],
        ]
    result = inspect_schema(connection=db, schema=namespace, table=name)
    assert result["success"], result
    item = result["tables"][0]
    assert item["name"] == name
    assert item["columns"][0]["name"] == "id"
    assert item["columns"][0]["data_type"]
    keys = dialect not in ("Access", "DSN")
    assert result["capabilities"]["primary_key"] is keys
    assert item["primary_key"] == (["id"] if keys else None)
    assert item["foreign_keys"] == ([] if keys else None)
    for call in cursor.execute.call_args_list:
        sql, params = call.args
        assert name not in sql  # Never paste even a quote-bearing name into SQL.
        assert name in params
        if dialect == "Oracle":
            assert "?" not in sql and ":1" in sql
        elif dialect in ("PostgreSQL", "MySQL"):
            assert "?" not in sql and "%s" in sql
    if dialect == "MySQL":
        assert "BINARY" in cursor.execute.call_args_list[0].args[0]
    db.commit.assert_not_called()
    db.rollback.assert_not_called()
    db.close.assert_not_called()


@pytest.mark.parametrize("dialect", list(discovery._READERS))
def test_catalog_failures_are_errors_not_empty_results(dialect):
    db = MagicMock()
    db.type.dbms_id = dialect
    cursor = db._cursor.return_value.__enter__.return_value
    cursor.execute.side_effect = RuntimeError("credential-secret")
    cursor.tables.side_effect = RuntimeError("credential-secret")
    result = inspect_schema(connection=db)
    assert result["success"] is False
    assert result["error"]["code"] == "metadata_error"
    assert result["tables"] == []
    assert "credential-secret" not in json.dumps(result)
    db.rollback.assert_not_called()


@pytest.mark.parametrize("state", ["IM001", "HYC00", "HY000", "28000"])
def test_odbc_only_explicit_unsupported_errors_mean_unavailable(state):
    cursor = MagicMock()
    cursor.primaryKeys.side_effect = RuntimeError(state, "driver message")
    if state in ("IM001", "HYC00"):
        assert discovery._optional_catalog(cursor, "primaryKeys", table="x") is None
    else:
        with pytest.raises(RuntimeError):
            discovery._optional_catalog(cursor, "primaryKeys", table="x")


def test_odbc_keys_keep_column_order_and_filter_other_objects():
    db = MagicMock()
    db.type.dbms_id = "DSN"
    db.conn.getinfo.return_value = "\\"
    cursor = db._cursor.return_value.__enter__.return_value
    cursor.tables.return_value = [("cat", "public", "t%", "TABLE")]
    cursor.columns.return_value = []
    cursor.primaryKeys.return_value = [("cat", "public", "t%", "b", 2, "pk"), ("cat", "public", "t%", "a", 1, "pk")]
    cursor.foreignKeys.return_value = [
        ("cat", "public", "p", "b", "cat", "public", "t%", "y", 2, 0, 0, "fk"),
        ("cat", "public", "p", "a", "cat", "public", "t%", "x", 1, 0, 0, "fk"),
    ]
    result = inspect_schema(connection=db, table="t%")
    assert result["success"]
    assert result["adapter"] == "DSN" and result["dialect"] is None
    assert result["capabilities"]["primary_key"] is True
    assert result["tables"][0]["primary_key"] == ["a", "b"]
    assert result["tables"][0]["foreign_keys"][0]["columns"] == ["x", "y"]
    assert result["tables"][0]["foreign_keys"][0]["referenced_columns"] == ["a", "b"]


def test_sqlite_inspection_works_when_reading_user_rows_is_forbidden(sqlite_db):
    import sqlite3

    db = sqlite_db
    db.conn.execute("CREATE TABLE secrets (value TEXT)")
    db.conn.execute("INSERT INTO secrets VALUES ('private')")
    reads = []

    def authorize(operation, object_name, column, schema, source):
        if operation == sqlite3.SQLITE_READ:
            reads.append(object_name)
            if object_name == "secrets":
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    db.conn.set_authorizer(authorize)
    try:
        result = inspect_schema(connection=db, table="secrets")
        assert result["success"]
        assert result["tables"][0]["columns"][0]["name"] == "value"
        assert "secrets" not in reads
        assert "private" not in json.dumps(result)
    finally:
        db.conn.set_authorizer(None)


def test_sqlite_unresolvable_parent_key_is_explicit(sqlite_db):
    sqlite_db.conn.execute("CREATE TABLE child(v INT REFERENCES missing_parent)")
    result = inspect_schema(connection=sqlite_db, table="child")
    assert result["success"]
    assert result["tables"][0]["foreign_keys"][0]["referenced_columns"] == [None]


@pytest.mark.parametrize("filtered", [False, True])
@pytest.mark.parametrize("name", ["t\\_", "t\\%", "t%_", "t\\"])
@pytest.mark.parametrize("escape", ["\\", "!", ""])
def test_odbc_exact_filters_escape_driver_patterns(filtered, name, escape):
    import re

    namespace, catalog = "s" + escape + "_", "catalog%_\\"
    identity = (catalog, namespace, name)

    def matches(value, pattern):
        if pattern is None:
            return True
        expression, index = "", 0
        while index < len(pattern):
            char = pattern[index]
            if escape and char == escape and index + 1 < len(pattern):
                index += 1
                expression += re.escape(pattern[index])
            else:
                expression += {"%": ".*", "_": "."}.get(char, re.escape(char))
            index += 1
        return re.fullmatch(expression, value) is not None

    class Cursor:
        def tables(self, *, table, schema, tableType):
            return [(*identity, "TABLE")] if matches(name, table) and matches(namespace, schema) else []

        def columns(self, *, table, schema, catalog):
            assert catalog == identity[0]  # SQLColumns catalog is literal.
            if not matches(name, table) or not matches(namespace, schema):
                return []
            row = [None] * 18
            row[:4] = [*identity, "id"]
            row[5], row[10], row[16] = "INTEGER", 0, 1
            return [row]

        def primaryKeys(self, **filters):
            assert filters == {"table": name, "schema": namespace, "catalog": catalog}
            return []

        def foreignKeys(self, **filters):
            assert filters == {"foreignTable": name, "foreignSchema": namespace, "foreignCatalog": catalog}
            return []

    db = MagicMock()
    db.type.dbms_id = "DSN"
    db.conn.getinfo.return_value = escape
    db._cursor.return_value.__enter__.return_value = Cursor()
    result = inspect_schema(connection=db, schema=namespace if filtered else None, table=name if filtered else None)
    assert result["success"], result
    assert len(result["tables"]) == 1
    assert result["tables"][0]["name"] == name
    assert result["tables"][0]["columns"][0]["name"] == "id"


@pytest.mark.parametrize("dbms", ["mysql", "mariadb"])
def test_mysql_primary_keys_distinguish_case_sensitive_table_names(dbms, tmp_path):
    db = open_backend(dbms, tmp_path)
    lower, upper = "discovery_case", "discovery_Case"
    created = []
    try:
        with db._cursor() as cursor:
            cursor.execute("SELECT @@lower_case_table_names")
            if cursor.fetchone()[0] != 0:
                pytest.skip("Server folds table names; case-distinct objects cannot exist")
        db.execute(f"CREATE TABLE {lower} (lower_id INT PRIMARY KEY)")
        created.append(lower)
        db.execute(f"CREATE TABLE {upper} (upper_id INT PRIMARY KEY)")
        created.append(upper)
        for name, column in ((lower, "lower_id"), (upper, "upper_id")):
            result = inspect_schema(connection=db, table=name)
            assert result["success"]
            assert [t["name"] for t in result["tables"]] == [name]
            assert result["tables"][0]["primary_key"] == [column]
    finally:
        for name in reversed(created):
            db.execute(f"DROP TABLE IF EXISTS {name}")
        db.close()


@pytest.mark.parametrize("stream", [None, SimpleNamespace(isatty=lambda: False)])
def test_api_password_prompt_requires_a_terminal(monkeypatch, stream):
    monkeypatch.setattr("sys.stdin", stream)
    with pytest.raises(ValueError, match="interactive terminal"):
        inspect_schema(dsn="postgresql://user@host/db", prompt_password=True)


def test_explicit_api_prompt_is_forwarded_without_changing_default_ownership(sqlite_db, monkeypatch):
    from unittest.mock import MagicMock

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    connect = MagicMock(return_value=sqlite_db)
    monkeypatch.setattr("execsql.api._connect_from_dsn", connect)
    assert inspect_schema(dsn="sqlite:///:memory:", prompt_password=True)["success"]
    assert connect.call_args.kwargs["prompt_password"] is True
    assert sqlite_db.conn is None
