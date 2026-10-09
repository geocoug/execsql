"""Integration tests that run SQL scripts through the full execsql pipeline using MySQL/MariaDB.

Mirrors the SQLite integration tests in test_sqlite.py but uses MySQL as
the backend (db_type = m).  Each test writes a minimal execsql.conf, creates a
.sql script with metacommands, invokes the CLI via subprocess, and asserts
outcomes.

The entire module is skipped when:
  1. pymysql is not installed, or
  2. the test MySQL server is not reachable at localhost:3306 with the
     credentials below.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import textwrap

import pytest

from tests.integration.conftest import write_script

# ---------------------------------------------------------------------------
# Module-level skip: require pymysql and a reachable MySQL server
# ---------------------------------------------------------------------------

pymysql = pytest.importorskip("pymysql", reason="pymysql package required")

_MYSQL_HOST = os.environ.get("EXECSQL_MYSQL_HOST", "localhost")
_MYSQL_PORT = int(os.environ.get("EXECSQL_MYSQL_PORT", "3306"))
_MYSQL_DB = os.environ.get("EXECSQL_MYSQL_DATABASE", "execsql_test")
_MYSQL_USER = os.environ.get("EXECSQL_MYSQL_USER", "execsql")
_MYSQL_PASSWORD = os.environ.get("EXECSQL_MYSQL_PASSWORD", "execsql")

_MYSQL_CONNECT_KWARGS: dict = {
    "host": _MYSQL_HOST,
    "port": _MYSQL_PORT,
    "database": _MYSQL_DB,
    "user": _MYSQL_USER,
    "password": _MYSQL_PASSWORD,
    "connect_timeout": 3,
}


def _mysql_is_reachable() -> bool:
    """Return True if a TCP connection to the MySQL server succeeds."""
    try:
        conn = pymysql.connect(**_MYSQL_CONNECT_KWARGS)
        conn.close()
        return True
    except Exception:  # noqa: BLE001
        return False


if not _mysql_is_reachable():
    pytest.skip(
        f"MySQL server not reachable at {_MYSQL_HOST}:{_MYSQL_PORT} (database={_MYSQL_DB}, user={_MYSQL_USER})",
        allow_module_level=True,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_MYSQL_DSN = f"mysql://{_MYSQL_USER}:{_MYSQL_PASSWORD}@{_MYSQL_HOST}:{_MYSQL_PORT}/{_MYSQL_DB}"


def _write_conf(tmp_path, extra=""):
    """Write a minimal execsql.conf for MySQL into *tmp_path*."""
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


def _run_execsql_mysql(tmp_path, script_path, extra_args=None, timeout=30):
    """Run execsql on the given script via subprocess, connecting via --dsn."""
    cmd = [sys.executable, "-m", "execsql", "run", "--dsn", _MYSQL_DSN, str(script_path)]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(
        cmd,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _query_mysql(sql: str):
    """Connect to the test MySQL database, run *sql*, and return all rows."""
    conn = pymysql.connect(**_MYSQL_CONNECT_KWARGS)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            return list(cur.fetchall())
    finally:
        conn.close()


def _exec_mysql(sql: str):
    """Execute a non-SELECT statement against the test MySQL database."""
    conn = pymysql.connect(**_MYSQL_CONNECT_KWARGS)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test: basic SQL execution (CREATE TABLE, INSERT, SELECT)
# ---------------------------------------------------------------------------


class TestBasicSQLExecution:
    def test_create_table_and_insert(self, tmp_path):
        """CREATE TABLE + INSERT via execsql, then verify rows in the DB."""
        _exec_mysql("DROP TABLE IF EXISTS fruits")
        _write_conf(tmp_path)
        script = write_script(
            tmp_path,
            """\
            CREATE TABLE fruits (
                id INTEGER PRIMARY KEY,
                name VARCHAR(255) NOT NULL
            ) ENGINE=InnoDB;

            INSERT INTO fruits (id, name) VALUES (1, 'apple');
            INSERT INTO fruits (id, name) VALUES (2, 'banana');
            INSERT INTO fruits (id, name) VALUES (3, 'cherry');
            """,
        )

        result = _run_execsql_mysql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_mysql("SELECT id, name FROM fruits ORDER BY id")
        assert len(rows) == 3
        assert rows[0] == (1, "apple")
        assert rows[1] == (2, "banana")
        assert rows[2] == (3, "cherry")

        _exec_mysql("DROP TABLE IF EXISTS fruits")


# ---------------------------------------------------------------------------
# Test: substitution variables (SUB metacommand)
# ---------------------------------------------------------------------------


class TestSubstitutionVariables:
    def test_sub_variable_in_insert(self, tmp_path):
        """Define a SUB variable and use it in a SQL INSERT."""
        _exec_mysql("DROP TABLE IF EXISTS greetings")
        _write_conf(tmp_path)
        script = write_script(
            tmp_path,
            """\
            CREATE TABLE greetings (msg VARCHAR(255)) ENGINE=InnoDB;

            -- !x! SUB myvar Hello World
            INSERT INTO greetings (msg) VALUES ('!!myvar!!');
            """,
        )

        result = _run_execsql_mysql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_mysql("SELECT msg FROM greetings")
        assert len(rows) == 1
        assert rows[0][0] == "Hello World"

        _exec_mysql("DROP TABLE IF EXISTS greetings")


# ---------------------------------------------------------------------------
# Test: EXPORT to CSV
# ---------------------------------------------------------------------------


class TestExportCSV:
    def test_export_query_to_csv(self, tmp_path):
        """Run a SELECT and export results to a CSV file, then verify contents."""
        _exec_mysql("DROP TABLE IF EXISTS items")
        _write_conf(tmp_path)
        csv_path = tmp_path / "output.csv"
        script = write_script(
            tmp_path,
            f"""\
            CREATE TABLE items (id INTEGER, label VARCHAR(255)) ENGINE=InnoDB;
            INSERT INTO items VALUES (1, 'alpha');
            INSERT INTO items VALUES (2, 'beta');
            INSERT INTO items VALUES (3, 'gamma');

            -- !x! EXPORT QUERY << SELECT id, label FROM items ORDER BY id; >> TO {csv_path} AS CSV
            """,
        )

        result = _run_execsql_mysql(tmp_path, script)
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

        _exec_mysql("DROP TABLE IF EXISTS items")


# ---------------------------------------------------------------------------
# Test: IMPORT from CSV
# ---------------------------------------------------------------------------


class TestImportCSV:
    def test_import_csv_into_table(self, tmp_path):
        """Import a CSV file into a pre-created table and verify row counts."""
        _exec_mysql("DROP TABLE IF EXISTS students")
        _write_conf(tmp_path)

        csv_path = tmp_path / "data.csv"
        csv_path.write_text("id,name,score\n1,Alice,95\n2,Bob,87\n3,Carol,92\n")

        script = write_script(
            tmp_path,
            f"""\
            CREATE TABLE students (id INTEGER, name VARCHAR(255), score INTEGER) ENGINE=InnoDB;

            -- !x! TRIM_STRINGS YES
            -- !x! IMPORT TO students FROM {csv_path}
            """,
        )

        result = _run_execsql_mysql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_mysql("SELECT id, name, score FROM students ORDER BY id")
        assert len(rows) == 3
        assert rows[0] == (1, "Alice", 95)
        assert rows[1] == (2, "Bob", 87)
        assert rows[2] == (3, "Carol", 92)

        _exec_mysql("DROP TABLE IF EXISTS students")


class TestImportToNewWithTheNameInAnotherDatabase:
    """TO NEW checks the connection's own database, not every database the login can see."""

    _OTHER = "execsql_other"

    def _as_root(self, sql: str) -> None:
        kwargs = {
            **_MYSQL_CONNECT_KWARGS,
            "user": "root",
            "password": os.environ.get("EXECSQL_MYSQL_ROOT_PASSWORD", "root"),
        }
        kwargs.pop("database")
        try:
            conn = pymysql.connect(**kwargs)
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"needs root on the test server to create a second database: {exc}")
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(sql)
        finally:
            conn.close()

    def test_a_table_in_another_database_does_not_block_import_to_new(self, tmp_path):
        self._as_root(f"CREATE DATABASE IF NOT EXISTS {self._OTHER}")
        self._as_root(f"CREATE TABLE IF NOT EXISTS {self._OTHER}.two (z INTEGER)")
        self._as_root(f"GRANT SELECT ON {self._OTHER}.* TO '{_MYSQL_USER}'@'%'")
        _exec_mysql("DROP TABLE IF EXISTS two")
        _write_conf(tmp_path)
        csv_path = tmp_path / "two.csv"
        csv_path.write_text("a,b\n1,2\n")
        script = write_script(tmp_path, f"-- !x! IMPORT TO NEW two FROM {csv_path}\n")
        try:
            result = _run_execsql_mysql(tmp_path, script)
            assert result.returncode == 0, f"stderr: {result.stderr}"
            assert _query_mysql("SELECT a, b FROM two") == [(1, 2)]
        finally:
            _exec_mysql("DROP TABLE IF EXISTS two")
            self._as_root(f"DROP DATABASE IF EXISTS {self._OTHER}")


# ---------------------------------------------------------------------------
# Test: conditional execution (IF / ENDIF)
# ---------------------------------------------------------------------------


class TestConditionalExecution:
    def test_if_true_branch_executes(self, tmp_path):
        """IF condition is true: the block inside executes."""
        _exec_mysql("DROP TABLE IF EXISTS results")
        _write_conf(tmp_path)
        script = write_script(
            tmp_path,
            """\
            CREATE TABLE results (branch VARCHAR(255)) ENGINE=InnoDB;

            -- !x! SUB testval 1
            -- !x! IF (EQUALS(!!testval!!, 1))
            INSERT INTO results VALUES ('true_branch');
            -- !x! ENDIF
            """,
        )

        result = _run_execsql_mysql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_mysql("SELECT branch FROM results")
        assert rows == [("true_branch",)]

        _exec_mysql("DROP TABLE IF EXISTS results")

    def test_if_else(self, tmp_path):
        """IF/ELSE: the ELSE branch executes when the condition is false."""
        _exec_mysql("DROP TABLE IF EXISTS results")
        _write_conf(tmp_path)
        script = write_script(
            tmp_path,
            """\
            CREATE TABLE results (branch VARCHAR(255)) ENGINE=InnoDB;

            -- !x! SUB testval 99
            -- !x! IF (EQUALS(!!testval!!, 1))
            INSERT INTO results VALUES ('if_branch');
            -- !x! ELSE
            INSERT INTO results VALUES ('else_branch');
            -- !x! ENDIF
            """,
        )

        result = _run_execsql_mysql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_mysql("SELECT branch FROM results")
        assert rows == [("else_branch",)]

        _exec_mysql("DROP TABLE IF EXISTS results")


# ---------------------------------------------------------------------------
# Test: DDL — views
# ---------------------------------------------------------------------------


class TestDDLOperations:
    def test_create_view(self, tmp_path):
        """Create a view and verify it exists."""
        _exec_mysql("DROP VIEW IF EXISTS eng_employees")
        _exec_mysql("DROP TABLE IF EXISTS employees")
        _write_conf(tmp_path)
        script = write_script(
            tmp_path,
            """\
            CREATE TABLE employees (id INTEGER, name VARCHAR(255), dept VARCHAR(255)) ENGINE=InnoDB;
            INSERT INTO employees VALUES (1, 'Alice', 'eng');
            INSERT INTO employees VALUES (2, 'Bob', 'sales');
            INSERT INTO employees VALUES (3, 'Carol', 'eng');

            CREATE VIEW eng_employees AS
                SELECT id, name FROM employees WHERE dept = 'eng';
            """,
        )

        result = _run_execsql_mysql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_mysql("SELECT name FROM eng_employees ORDER BY name")
        assert rows == [("Alice",), ("Carol",)]

        _exec_mysql("DROP VIEW IF EXISTS eng_employees")
        _exec_mysql("DROP TABLE IF EXISTS employees")

    def test_drop_and_recreate_table(self, tmp_path):
        """Drop a table and recreate it with a different schema."""
        _exec_mysql("DROP TABLE IF EXISTS tmp_rebuild")
        _write_conf(tmp_path)
        script = write_script(
            tmp_path,
            """\
            CREATE TABLE tmp_rebuild (val INTEGER) ENGINE=InnoDB;
            INSERT INTO tmp_rebuild VALUES (1);
            DROP TABLE tmp_rebuild;
            CREATE TABLE tmp_rebuild (val VARCHAR(255)) ENGINE=InnoDB;
            INSERT INTO tmp_rebuild VALUES ('rebuilt');
            """,
        )

        result = _run_execsql_mysql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_mysql("SELECT val FROM tmp_rebuild")
        assert rows == [("rebuilt",)]

        _exec_mysql("DROP TABLE IF EXISTS tmp_rebuild")


# ---------------------------------------------------------------------------
# Test: export to JSON
# ---------------------------------------------------------------------------


class TestExportJSON:
    def test_export_query_to_json(self, tmp_path):
        """Export query results to a JSON file."""
        _exec_mysql("DROP TABLE IF EXISTS items")
        _write_conf(tmp_path)
        out = tmp_path / "output.json"
        script = write_script(
            tmp_path,
            f"""\
            CREATE TABLE items (id INTEGER, label VARCHAR(255)) ENGINE=InnoDB;
            INSERT INTO items VALUES (1, 'alpha');
            INSERT INTO items VALUES (2, 'beta');

            -- !x! EXPORT QUERY << SELECT id, label FROM items ORDER BY id; >> TO {out} AS JSON
            """,
        )

        result = _run_execsql_mysql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert out.exists()

        data = json.loads(out.read_text())
        assert len(data) == 2
        assert data[0]["id"] == 1
        assert data[0]["label"] == "alpha"
        assert data[1]["id"] == 2
        assert data[1]["label"] == "beta"

        _exec_mysql("DROP TABLE IF EXISTS items")


class TestImportBackslashes:
    r"""``LOAD DATA`` keeps backslashes in the data and in the file path, as every other backend does.

    MySQL's default ``ESCAPED BY '\\'`` turned ``C:\new\tbl`` into a newline
    and a tab, ``\N`` into NULL, and a backslash in the file path into an
    escape inside the quoted file name.
    """

    VALUES = [r"C:\new\tbl", r"\N", r"a\\b", r"regex \d+\s*", r"\toc"]

    def _import(self, tmp_path, directory):
        directory.mkdir(parents=True, exist_ok=True)
        csv = directory / "paths.csv"
        csv.write_text("id,val\n" + "".join(f"{i},{v}\n" for i, v in enumerate(self.VALUES)), encoding="utf-8")
        _exec_mysql("DROP TABLE IF EXISTS backslashes")
        _exec_mysql("CREATE TABLE backslashes (id INTEGER, val VARCHAR(100))")
        try:
            script = write_script(tmp_path, f"-- !x! IMPORT TO backslashes FROM {csv}\n")
            result = _run_execsql_mysql(tmp_path, script)
            assert result.returncode == 0, f"stderr: {result.stderr}"
            return [row[0] for row in _query_mysql("SELECT val FROM backslashes ORDER BY id")]
        finally:
            _exec_mysql("DROP TABLE IF EXISTS backslashes")

    def test_backslashes_in_values_are_kept(self, tmp_path):
        assert self._import(tmp_path, tmp_path / "plain") == self.VALUES

    def test_a_backslash_in_the_file_path_is_kept(self, tmp_path):
        assert self._import(tmp_path, tmp_path / "dir\\with\\backslashes") == self.VALUES
