"""Integration tests that run SQL scripts through the full execsql pipeline using PostgreSQL.

Mirrors the SQLite integration tests in test_sqlite.py but uses PostgreSQL as
the backend (db_type = p).  Each test writes a minimal execsql.conf, creates a
.sql script with metacommands, invokes the CLI via subprocess, and asserts
outcomes (tables created, data inserted, files exported, etc.).

The entire module is skipped when:
  - psycopg2 is not installed, OR
  - the test PostgreSQL instance (localhost:5432, database=execsql_test,
    user=execsql, password=execsql) is not reachable.
"""

from __future__ import annotations

import csv
import json
import os
import textwrap

import pytest

from tests.integration.conftest import write_script

# ---------------------------------------------------------------------------
# Module-level skip: psycopg2 availability + server reachability
# ---------------------------------------------------------------------------

psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 package required")

_PG_CONNECT_KWARGS: dict = {
    "host": os.environ.get("EXECSQL_PG_HOST", "localhost"),
    "port": int(os.environ.get("EXECSQL_PG_PORT", "5432")),
    "dbname": os.environ.get("EXECSQL_PG_DATABASE", "execsql_test"),
    "user": os.environ.get("EXECSQL_PG_USER", "execsql"),
    "password": os.environ.get("EXECSQL_PG_PASSWORD", "execsql"),
    "connect_timeout": 3,
}


def _pg_is_reachable() -> bool:
    """Return True if the test PostgreSQL instance is connectable."""
    try:
        conn = psycopg2.connect(**_PG_CONNECT_KWARGS)
        conn.close()
        return True
    except Exception:  # noqa: BLE001
        return False


if not _pg_is_reachable():
    pytest.skip(
        "PostgreSQL test instance not reachable at localhost:5432 (database=execsql_test, user=execsql)",
        allow_module_level=True,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_PG_DSN = (
    f"postgresql://{_PG_CONNECT_KWARGS['user']}:{_PG_CONNECT_KWARGS['password']}"
    f"@{_PG_CONNECT_KWARGS['host']}:{_PG_CONNECT_KWARGS['port']}"
    f"/{_PG_CONNECT_KWARGS['dbname']}"
)


def _write_conf(tmp_path, extra=""):
    """Write a minimal execsql.conf for PostgreSQL into *tmp_path*."""
    conf = tmp_path / "execsql.conf"
    conf.write_text(
        textwrap.dedent(f"""\
        [encoding]
        script = utf-8
        output = utf-8
        import = utf-8
        {extra}
    """),
    )
    return conf


def _run_execsql_pg(tmp_path, script_path, extra_args=None, timeout=30):
    """Run execsql on the given script via subprocess, connecting via --dsn."""
    import subprocess
    import sys

    cmd = [sys.executable, "-m", "execsql", "--dsn", _PG_DSN, str(script_path)]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(
        cmd,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _query_pg(sql: str, params=None):
    """Open a connection to the test PostgreSQL database, run *sql*, and return all rows."""
    conn = psycopg2.connect(**_PG_CONNECT_KWARGS)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


def _exec_pg(sql: str, params=None):
    """Execute a non-SELECT statement against the test PostgreSQL database."""
    conn = psycopg2.connect(**_PG_CONNECT_KWARGS)
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(sql, params)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test: basic SQL execution (CREATE TABLE, INSERT, SELECT)
# ---------------------------------------------------------------------------


class TestBasicSQLExecution:
    def test_create_table_and_insert(self, tmp_path):
        """CREATE TABLE + INSERT via execsql, then verify rows in the DB."""
        _exec_pg("DROP TABLE IF EXISTS fruits")
        _write_conf(tmp_path)
        script = write_script(
            tmp_path,
            """\
            CREATE TABLE fruits (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );

            INSERT INTO fruits (id, name) VALUES (1, 'apple');
            INSERT INTO fruits (id, name) VALUES (2, 'banana');
            INSERT INTO fruits (id, name) VALUES (3, 'cherry');
            """,
        )

        result = _run_execsql_pg(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_pg("SELECT id, name FROM fruits ORDER BY id")
        assert len(rows) == 3
        assert rows[0] == (1, "apple")
        assert rows[1] == (2, "banana")
        assert rows[2] == (3, "cherry")

        _exec_pg("DROP TABLE IF EXISTS fruits")


# ---------------------------------------------------------------------------
# Test: substitution variables (SUB metacommand)
# ---------------------------------------------------------------------------


class TestSubstitutionVariables:
    def test_sub_variable_in_insert(self, tmp_path):
        """Define a SUB variable and use it in a SQL INSERT."""
        _exec_pg("DROP TABLE IF EXISTS greetings")
        _write_conf(tmp_path)
        script = write_script(
            tmp_path,
            """\
            CREATE TABLE greetings (msg TEXT);

            -- !x! SUB myvar Hello World
            INSERT INTO greetings (msg) VALUES ('!!myvar!!');
            """,
        )

        result = _run_execsql_pg(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_pg("SELECT msg FROM greetings")
        assert len(rows) == 1
        assert rows[0][0] == "Hello World"

        _exec_pg("DROP TABLE IF EXISTS greetings")


# ---------------------------------------------------------------------------
# Test: EXPORT to CSV
# ---------------------------------------------------------------------------


class TestExportCSV:
    def test_export_query_to_csv(self, tmp_path):
        """Run a SELECT and export results to a CSV file, then verify contents."""
        _exec_pg("DROP TABLE IF EXISTS items")
        _write_conf(tmp_path)
        csv_path = tmp_path / "output.csv"
        script = write_script(
            tmp_path,
            f"""\
            CREATE TABLE items (id INTEGER, label TEXT);
            INSERT INTO items VALUES (1, 'alpha');
            INSERT INTO items VALUES (2, 'beta');
            INSERT INTO items VALUES (3, 'gamma');

            -- !x! EXPORT QUERY << SELECT id, label FROM items ORDER BY id; >> TO {csv_path} AS CSV
            """,
        )

        result = _run_execsql_pg(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        assert csv_path.exists(), "CSV file was not created"
        with open(csv_path, newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # First row should be headers
        assert rows[0] == ["id", "label"]
        assert len(rows) == 4  # header + 3 data rows
        assert rows[1] == ["1", "alpha"]
        assert rows[2] == ["2", "beta"]
        assert rows[3] == ["3", "gamma"]

        _exec_pg("DROP TABLE IF EXISTS items")


# ---------------------------------------------------------------------------
# Test: IMPORT from CSV
# ---------------------------------------------------------------------------


class TestImportCSV:
    def test_import_csv_into_table(self, tmp_path):
        """Import a CSV file into a table and verify row counts."""
        _exec_pg("DROP TABLE IF EXISTS students")
        _write_conf(tmp_path)

        # Write the CSV file to import
        csv_path = tmp_path / "data.csv"
        csv_path.write_text("id,name,score\n1,Alice,95\n2,Bob,87\n3,Carol,92\n")

        script = write_script(
            tmp_path,
            f"""\
            CREATE TABLE students (id INTEGER, name TEXT, score INTEGER);

            -- !x! IMPORT TO students FROM {csv_path}
            """,
        )

        result = _run_execsql_pg(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_pg("SELECT id, name, score FROM students ORDER BY id")
        assert len(rows) == 3
        assert rows[0] == (1, "Alice", 95)
        assert rows[1] == (2, "Bob", 87)
        assert rows[2] == (3, "Carol", 92)

        _exec_pg("DROP TABLE IF EXISTS students")


# ---------------------------------------------------------------------------
# Test: conditional execution (IF / ENDIF)
# ---------------------------------------------------------------------------


class TestConditionalExecution:
    def test_if_true_branch_executes(self, tmp_path):
        """IF condition is true: the block inside executes."""
        _exec_pg("DROP TABLE IF EXISTS results")
        _write_conf(tmp_path)
        script = write_script(
            tmp_path,
            """\
            CREATE TABLE results (branch TEXT);

            -- !x! SUB testval 1
            -- !x! IF (EQUALS(!!testval!!, 1))
            INSERT INTO results VALUES ('true_branch');
            -- !x! ENDIF
            """,
        )

        result = _run_execsql_pg(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_pg("SELECT branch FROM results")
        assert rows == [("true_branch",)]

        _exec_pg("DROP TABLE IF EXISTS results")

    def test_if_else(self, tmp_path):
        """IF/ELSE: the ELSE branch executes when the condition is false."""
        _exec_pg("DROP TABLE IF EXISTS results")
        _write_conf(tmp_path)
        script = write_script(
            tmp_path,
            """\
            CREATE TABLE results (branch TEXT);

            -- !x! SUB testval 99
            -- !x! IF (EQUALS(!!testval!!, 1))
            INSERT INTO results VALUES ('if_branch');
            -- !x! ELSE
            INSERT INTO results VALUES ('else_branch');
            -- !x! ENDIF
            """,
        )

        result = _run_execsql_pg(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_pg("SELECT branch FROM results")
        assert rows == [("else_branch",)]

        _exec_pg("DROP TABLE IF EXISTS results")


# ---------------------------------------------------------------------------
# Test: DDL — views, DROP and recreate
# ---------------------------------------------------------------------------


class TestDDLOperations:
    def test_create_view(self, tmp_path):
        """Create a view and verify it can be queried directly."""
        _exec_pg("DROP VIEW IF EXISTS eng_employees")
        _exec_pg("DROP TABLE IF EXISTS employees")
        _write_conf(tmp_path)
        script = write_script(
            tmp_path,
            """\
            CREATE TABLE employees (id INTEGER, name TEXT, dept TEXT);
            INSERT INTO employees VALUES (1, 'Alice', 'eng');
            INSERT INTO employees VALUES (2, 'Bob', 'sales');
            INSERT INTO employees VALUES (3, 'Carol', 'eng');

            CREATE VIEW eng_employees AS
                SELECT id, name FROM employees WHERE dept = 'eng';
            """,
        )

        result = _run_execsql_pg(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_pg("SELECT name FROM eng_employees ORDER BY name")
        assert rows == [("Alice",), ("Carol",)]

        _exec_pg("DROP VIEW IF EXISTS eng_employees")
        _exec_pg("DROP TABLE IF EXISTS employees")

    def test_drop_and_recreate_table(self, tmp_path):
        """Drop a table and recreate it with a different schema."""
        _exec_pg("DROP TABLE IF EXISTS tmp_pg")
        _write_conf(tmp_path)
        script = write_script(
            tmp_path,
            """\
            CREATE TABLE tmp_pg (val INTEGER);
            INSERT INTO tmp_pg VALUES (1);
            DROP TABLE tmp_pg;
            CREATE TABLE tmp_pg (val TEXT);
            INSERT INTO tmp_pg VALUES ('rebuilt');
            """,
        )

        result = _run_execsql_pg(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_pg("SELECT val FROM tmp_pg")
        assert rows == [("rebuilt",)]

        _exec_pg("DROP TABLE IF EXISTS tmp_pg")


# ---------------------------------------------------------------------------
# Test: export to JSON
# ---------------------------------------------------------------------------


class TestExportJSON:
    def test_export_query_to_json(self, tmp_path):
        """Export query results to a JSON file and verify structure."""
        _exec_pg("DROP TABLE IF EXISTS items")
        _write_conf(tmp_path)
        out = tmp_path / "output.json"
        script = write_script(
            tmp_path,
            f"""\
            CREATE TABLE items (id INTEGER, label TEXT);
            INSERT INTO items VALUES (1, 'alpha');
            INSERT INTO items VALUES (2, 'beta');

            -- !x! EXPORT QUERY << SELECT id, label FROM items ORDER BY id; >> TO {out} AS JSON
            """,
        )

        result = _run_execsql_pg(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert out.exists()

        data = json.loads(out.read_text())
        assert len(data) == 2
        assert data[0]["id"] == 1
        assert data[0]["label"] == "alpha"
        assert data[1]["id"] == 2
        assert data[1]["label"] == "beta"

        _exec_pg("DROP TABLE IF EXISTS items")
