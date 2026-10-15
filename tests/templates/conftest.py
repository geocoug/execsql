"""Run the scripts in templates/ against live databases.

Each template is a library of execsql scripts that a host script reads with INCLUDE and
then calls with EXECUTE SCRIPT.  A test does the same through
:func:`execsql.run`, whose result carries the errors and the final value of
every substitution variable, and reads what the scripts left in the database
with the driver directly.

The ``target`` fixture runs a test once per DBMS a template family supports:
PostgreSQL (``pg_``), MySQL and MariaDB (both ``md_``) and SQL Server (``ss_``).  Each
reads the same connection settings as the integration tests and skips when its
server is not reachable, so the suite stays green on a machine without them;
CI's integration job provides all three.  Locally::

    just test-templates

Every test works in namespaces of its own, created for it and dropped after
it: two schemas on PostgreSQL and SQL Server, two databases on MySQL and MariaDB
(which have no schemas inside a database).
"""

from __future__ import annotations

import csv
import os
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"


@dataclass
class Server:
    """How to reach one DBMS, and run statements on it outside execsql."""

    dbms: str
    prefix: str
    connect: Callable[[], object]
    dsn: Callable[[str], str]

    def execute(self, *statements: str) -> None:
        conn = self.connect()
        try:
            cur = conn.cursor()
            for sql in statements:
                cur.execute(sql)
            conn.commit()
        finally:
            conn.close()

    def query(self, sql: str) -> list[tuple]:
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute(sql)
            return [tuple(r) for r in cur.fetchall()]
        finally:
            conn.close()


def _postgres() -> Server:
    psycopg = pytest.importorskip("psycopg")
    kw = {
        "host": os.environ.get("EXECSQL_PG_HOST", "localhost"),
        "port": int(os.environ.get("EXECSQL_PG_PORT", "5432")),
        "dbname": os.environ.get("EXECSQL_PG_DATABASE", "execsql_test"),
        "user": os.environ.get("EXECSQL_PG_USER", "execsql"),
        "password": os.environ.get("EXECSQL_PG_PASSWORD", "execsql"),
    }
    return Server(
        "postgres",
        "pg",
        lambda: psycopg.connect(**kw, connect_timeout=3),
        lambda _db: f"postgresql://{kw['user']}:{kw['password']}@{kw['host']}:{kw['port']}/{kw['dbname']}",
    )


def _mysql_family(dbms: str, env: str, default_port: str) -> Server:
    pymysql = pytest.importorskip("pymysql")
    # Root, because each test creates and drops databases of its own.
    kw = {
        "host": os.environ.get(f"EXECSQL_{env}_HOST", "localhost"),
        "port": int(os.environ.get(f"EXECSQL_{env}_PORT", default_port)),
        "user": "root",
        "password": os.environ.get(f"EXECSQL_{env}_ROOT_PASSWORD", "root"),
    }
    return Server(
        dbms,
        "md",
        lambda: pymysql.connect(**kw, connect_timeout=3),
        lambda db: f"mysql://{kw['user']}:{kw['password']}@{kw['host']}:{kw['port']}/{db}",
    )


def _mysql() -> Server:
    return _mysql_family("mysql", "MYSQL", "3306")


def _mariadb() -> Server:
    # The md_ templates were written for MariaDB, which accepts SQL MySQL
    # rejects (CAST ... AS VARCHAR), so each is tested on both.
    return _mysql_family("mariadb", "MARIADB", "3307")


def _sqlserver() -> Server:
    pyodbc = pytest.importorskip("pyodbc")
    drivers = [d for d in pyodbc.drivers() if "SQL Server" in d]
    if not drivers:
        pytest.skip("no ODBC driver for SQL Server")
    host = os.environ.get("EXECSQL_MSSQL_HOST", "localhost")
    port = os.environ.get("EXECSQL_MSSQL_PORT", "1433")
    db = os.environ.get("EXECSQL_MSSQL_DATABASE", "execsql_test")
    user = os.environ.get("EXECSQL_MSSQL_USER", "sa")
    password = os.environ.get("EXECSQL_MSSQL_PASSWORD", "ExecSql_Test123!")

    def connect():
        conn = pyodbc.connect(
            f"DRIVER={{{drivers[-1]}}};SERVER={host},{port};UID={user};PWD={password};"
            "Encrypt=No;TrustServerCertificate=yes;",
            timeout=3,
            autocommit=True,
        )
        conn.execute(f"IF DB_ID('{db}') IS NULL CREATE DATABASE {db}")
        conn.execute(f"USE {db}")
        return conn

    return Server("sqlserver", "ss", connect, lambda _db: f"mssql://{user}:{password}@{host}:{port}/{db}")


_SERVERS = {"postgres": _postgres, "mysql": _mysql, "mariadb": _mariadb, "sqlserver": _sqlserver}
_REACHABLE: dict[str, Server | str] = {}


def _server(dbms: str) -> Server:
    """The server for *dbms*, or a skip if it is not reachable (checked once per session)."""
    if dbms not in _REACHABLE:
        try:
            server = _SERVERS[dbms]()
            server.query("select 1")
            _REACHABLE[dbms] = server
        except pytest.skip.Exception:
            raise
        except Exception as exc:  # any driver's connection failure
            _REACHABLE[dbms] = f"{dbms} not reachable: {type(exc).__name__}: {str(exc).splitlines()[0][:120]}"
    found = _REACHABLE[dbms]
    if isinstance(found, str):
        pytest.skip(found)
    return found


@dataclass
class Target:
    """One DBMS, with a base and a staging namespace made for the current test."""

    server: Server
    base: str
    staging: str
    request: pytest.FixtureRequest

    @property
    def dbms(self) -> str:
        return self.server.dbms

    def table(self, namespace: str, name: str) -> str:
        """A table's qualified name, as SQL outside the templates writes it."""
        return f"{namespace}.{name}"

    def base_table(self, name: str) -> str:
        return self.table(self.base, name)

    def staging_table(self, name: str) -> str:
        """The staging copy of table *name*.

        The MySQL templates take staging tables from the base database, named
        with a prefix (their ``stage_pfx`` argument, ``stg_`` here); the others
        take them from a staging schema of the same table name.
        """
        if self.server.prefix == "md":
            return self.table(self.base, f"stg_{name}")
        return self.table(self.staging, name)

    @property
    def staging_args(self) -> str:
        """The EXECUTE SCRIPT arguments that say where base and staging tables are."""
        if self.server.prefix == "md":
            return "stage_pfx=stg_"
        return f"base_schema={self.base}, staging={self.staging}"

    def template(self, family: str) -> Path:
        path = TEMPLATES / f"{self.server.prefix}_{family}.sql"
        if not path.is_file():
            pytest.skip(f"no {family} template for {self.dbms}")
        return path

    def execute(self, *statements: str) -> None:
        self.server.execute(*statements)

    def query(self, sql: str) -> list[tuple]:
        return self.server.query(sql)

    def run(self, family: str, body: str, *, tmp_path: Path, halt_on_error: bool = True):
        """INCLUDE the family's template, then run *body*; return the ScriptResult.

        The run connects to the base namespace's database (on MySQL, the base
        database; elsewhere the test database, with the namespaces as
        schemas).  Relative paths in *body* resolve in *tmp_path*.
        """
        from execsql import run

        sql = f'-- !x! INCLUDE "{self.template(family).as_posix()}"\n{body}'
        cwd = Path.cwd()
        os.chdir(tmp_path)
        try:
            return run(sql=sql, dsn=self.server.dsn(self.base), halt_on_error=halt_on_error)
        finally:
            os.chdir(cwd)


def _create(server: Server, name: str) -> None:
    if server.prefix == "md":
        server.execute(f"create database {name}")
    else:
        server.execute(f"create schema {name}")


def _drop(server: Server, name: str) -> None:
    if server.prefix == "md":
        server.execute(f"drop database if exists {name}")
    elif server.dbms == "postgres":
        server.execute(f"drop schema if exists {name} cascade")
    else:
        # SQL Server has no DROP SCHEMA ... CASCADE: drop the schema's views
        # and tables (foreign keys first), then the schema.
        rows = server.query(
            "select 'alter table ' + quotename(s.name) + '.' + quotename(t.name) + "
            "' drop constraint ' + quotename(f.name) from sys.foreign_keys f "
            "join sys.tables t on t.object_id = f.parent_object_id "
            f"join sys.schemas s on s.schema_id = t.schema_id where s.name = '{name}'",
        )
        rows += server.query(
            "select 'drop ' + case o.type when 'V' then 'view ' else 'table ' end + "
            "quotename(s.name) + '.' + quotename(o.name) from sys.objects o "
            f"join sys.schemas s on s.schema_id = o.schema_id where s.name = '{name}' and o.type in ('U', 'V')",
        )
        server.execute(*(r[0] for r in rows), f"if schema_id('{name}') is not null drop schema {name}")


@pytest.fixture(params=["postgres", "mysql", "mariadb", "sqlserver"])
def target(request) -> Iterator[Target]:
    server = _server(request.param)
    tag = uuid.uuid4().hex[:8]
    base, staging = f"tpl_base_{tag}", f"tpl_stg_{tag}"
    for name in (base, staging):
        _create(server, name)
    try:
        yield Target(server, base, staging, request)
    finally:
        for name in (staging, base):
            _drop(server, name)


def known_bug(target, dbms: str | tuple[str, ...], reason: str) -> None:
    """Mark the running test as a known template bug on *dbms*, to be fixed in the revamp.

    Strict: once the template is fixed the test passes, the xfail turns into
    a failure, and the marker has to be removed with the fix.
    """
    if target.dbms in ((dbms,) if isinstance(dbms, str) else dbms):
        target.request.applymarker(pytest.mark.xfail(reason=reason, strict=True))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
