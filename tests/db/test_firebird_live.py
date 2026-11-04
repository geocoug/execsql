"""Opt-in Firebird transaction tests; configure EXECSQL_FIREBIRD_DATABASE to run them.

Use a disposable database: each test creates uniquely named tables and may
install a transaction-commit trigger that rejects its own guard row.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from uuid import uuid4

import pytest

from execsql import run
from execsql.db.firebird import FirebirdDatabase

pytestmark = pytest.mark.xdist_group("live-firebird")


@dataclass
class _Server:
    options: dict
    db: FirebirdDatabase
    objects: list[tuple[str, str]] = field(default_factory=list)

    def create(self, kind, definition):
        name = f"F138_{uuid4().hex[:16].upper()}"
        self.db.conn.execute_immediate(f"CREATE {kind} {name} {definition}")
        self.db.conn.commit()
        self.objects.append((kind, name))
        return name

    def rows(self, table):
        with self.db._cursor() as cursor:
            cursor.execute(f"SELECT V FROM {table}")
            return cursor.fetchall()

    def observed(self, table):
        observer = FirebirdDatabase(**self.options)
        try:
            with observer._cursor() as cursor:
                cursor.execute(f"SELECT V FROM {table}")
                return cursor.fetchall()
        finally:
            observer.close()


@pytest.fixture
def server():
    database = os.environ.get("EXECSQL_FIREBIRD_DATABASE")
    if not database:
        pytest.skip("set EXECSQL_FIREBIRD_DATABASE to a disposable Firebird database")
    options = {
        "server_name": os.environ.get("EXECSQL_FIREBIRD_HOST", "localhost"),
        "db_name": database,
        "user_name": os.environ.get("EXECSQL_FIREBIRD_USER", "SYSDBA"),
        "password": os.environ.get("EXECSQL_FIREBIRD_PASSWORD", "masterkey"),
        "port": int(os.environ.get("EXECSQL_FIREBIRD_PORT", "3050")),
        "encoding": "UTF8",
    }
    # Configuring a backend makes connection/driver failures errors, not skips.
    instance = _Server(options, FirebirdDatabase(**options))
    try:
        yield instance
    finally:
        instance.db.conn.rollback()
        for kind, name in reversed(instance.objects):
            try:
                instance.db.conn.execute_immediate(f"DROP {kind} {name}")
                instance.db.conn.commit()
            except Exception:
                instance.db.conn.rollback()  # A test may already have dropped it.
        instance.db.close()


@pytest.mark.parametrize("mode", ["autocommit-off", "batch"])
def test_table_lookup_does_not_commit_held_rows(server, mode):
    table = server.create("TABLE", "(V INTEGER)")
    if mode == "autocommit-off":
        sql = (
            "-- !x! AUTOCOMMIT OFF\n"
            f"insert into {table} values (1);\n"
            f"-- !x! IF (TABLE_EXISTS({table})) {{ SUB found yes }}\n"
        )
    else:
        sql = (
            "-- !x! LOOP WHILE (TRUE)\n-- !x! BEGIN BATCH\n"
            f"insert into {table} values (1);\n"
            f"-- !x! IF (TABLE_EXISTS({table})) {{ SUB found yes }}\n"
            "-- !x! BREAK\n-- !x! END BATCH\n-- !x! END LOOP\n"
        )
    result = run(sql=sql, connection=server.db)
    assert result.success, result.errors
    assert result.variables["found"] == "yes"
    assert server.observed(table) == []
    assert server.rows(table) == ([(1,)] if mode == "autocommit-off" else [])


def _load_command(tmp_path, target, source, replacement=False):
    new = "REPLACEMENT" if replacement else "NEW"
    if source == "csv":
        path = tmp_path / "input.csv"
        path.write_text("V\nloaded\ncafé\n", encoding="utf-8")
        return "", f"IMPORT TO {new} {target} FROM {path}"
    if source == "json":
        path = tmp_path / "input.json"
        path.write_text('[{"V": "loaded"}, {"V": "café"}]', encoding="utf-8")
        return "", f"IMPORT TO {new} {target} FROM JSON {path}"
    setup = (
        f"-- !x! CONNECT TO SQLITE(FILE={tmp_path / 'source.db'}, NEW) AS source\n"
        "-- !x! USE source\ncreate table src (V text);\n"
        "insert into src values ('loaded');\ninsert into src values ('café');\n-- !x! USE initial\n"
    )
    return setup, f"COPY src FROM source TO {new} {target} IN initial"


def _commit_guard(server):
    guard = server.create("TABLE", "(V INTEGER)")
    error = server.create("EXCEPTION", "'commit rejected'")
    server.create(
        "TRIGGER",
        "ACTIVE ON TRANSACTION COMMIT POSITION 0 AS BEGIN "
        f"IF (EXISTS(SELECT 1 FROM {guard} WHERE V = 1)) THEN EXCEPTION {error}; END",
    )
    return guard


@pytest.mark.parametrize("source", ["csv", "json", "copy"])
@pytest.mark.parametrize("replacement", [False, True])
def test_failed_ddl_commit_leaves_nothing_for_the_next_commit(server, tmp_path, source, replacement):
    target = server.create("TABLE", "(V VARCHAR(30))")
    if replacement:
        server.db.conn.execute_immediate(f"INSERT INTO {target} VALUES ('original')")
    else:
        server.db.conn.execute_immediate(f"DROP TABLE {target}")
    server.db.conn.commit()
    guard = _commit_guard(server)
    setup, command = _load_command(tmp_path, target, source, replacement)
    sql = (
        setup
        + "-- !x! ERROR_HALT OFF\n-- !x! METACOMMAND_ERROR_HALT OFF\n-- !x! AUTOCOMMIT OFF\n"
        + f"insert into {guard} values (1);\n-- !x! {command}\n-- !x! SUB reached_end yes\n"
    )
    result = run(sql=sql, connection=server.db)
    assert not result.success
    assert "commit rejected" in result.errors[0].message
    assert result.variables["reached_end"] == "yes"
    assert server.rows(guard) == []
    # Clear a pending guard (if a regression left it) so the following commit
    # would store the failed DDL as well. Neither failed CREATE nor DROP may survive.
    server.db.conn.execute_immediate(f"DELETE FROM {guard}")
    server.db.conn.commit()
    with server.db._cursor() as cursor:
        cursor.execute("SELECT RDB$RELATION_NAME FROM RDB$RELATIONS WHERE RDB$RELATION_NAME = ?", (target,))
        exists = bool(cursor.fetchall())
    assert exists is replacement
    if replacement:
        assert server.rows(target) == [("original",)]


@pytest.mark.parametrize("source", ["csv", "json", "copy"])
@pytest.mark.parametrize("autocommit", [True, False])
def test_successful_load_keeps_ddl_and_row_commit_boundaries(server, tmp_path, source, autocommit):
    target = server.create("TABLE", "(V VARCHAR(30))")
    server.db.conn.execute_immediate(f"DROP TABLE {target}")
    server.db.conn.commit()
    setup, command = _load_command(tmp_path, target, source)
    result = run(
        sql=setup + f"-- !x! AUTOCOMMIT {'ON' if autocommit else 'OFF'}\n-- !x! {command}\n",
        connection=server.db,
    )
    assert result.success, result.errors
    expected = [("loaded",), ("café",)]
    assert server.rows(target) == expected
    assert server.observed(target) == (expected if autocommit else [])


def test_a_catalog_commit_failure_rolls_back_the_transaction(server):
    guard = _commit_guard(server)
    server.db.conn.execute_immediate(f"INSERT INTO {guard} VALUES (1)")
    with pytest.raises(Exception, match="commit rejected"):
        server.db.table_exists(guard)
    assert server.rows(guard) == []
