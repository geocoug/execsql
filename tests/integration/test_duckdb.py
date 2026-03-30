"""Integration tests that run SQL scripts through the full execsql pipeline using DuckDB.

Mirrors the SQLite integration tests in test_sqlite.py but uses DuckDB as
the backend (db_type = k).  Each test writes a minimal execsql.conf, creates a
.sql script with metacommands, invokes the CLI via subprocess, and asserts
outcomes.
"""

from __future__ import annotations

import csv
import textwrap

import pytest

from tests.integration.conftest import run_execsql, write_script

duckdb = pytest.importorskip("duckdb", reason="duckdb package required")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_conf(tmp_path, db_filename="test.duckdb", extra=""):
    """Write a minimal execsql.conf for DuckDB into *tmp_path*."""
    conf = tmp_path / "execsql.conf"
    conf.write_text(
        textwrap.dedent(f"""\
        [connect]
        db_type = k
        db_file = {db_filename}
        new_db = yes
        password_prompt = no

        [encoding]
        script = utf-8
        output = utf-8
        import = utf-8
        {extra}
    """),
    )
    return conf


def _query_duckdb(db_path, sql):
    """Open a DuckDB file, run *sql*, and return all rows."""
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test: basic SQL execution (CREATE TABLE, INSERT, SELECT)
# ---------------------------------------------------------------------------


class TestBasicSQLExecution:
    def test_create_table_and_insert(self, tmp_path):
        """CREATE TABLE + INSERT via execsql, then verify rows in the DB."""
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

        result = run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        db_path = tmp_path / "test.duckdb"
        assert db_path.exists()

        rows = _query_duckdb(db_path, "SELECT id, name FROM fruits ORDER BY id")
        assert len(rows) == 3
        assert rows[0] == (1, "apple")
        assert rows[1] == (2, "banana")
        assert rows[2] == (3, "cherry")

    def test_multiple_statements(self, tmp_path):
        """Run multiple DDL/DML statements in sequence."""
        _write_conf(tmp_path)
        script = write_script(
            tmp_path,
            """\
            CREATE TABLE counters (name TEXT, val INTEGER);
            INSERT INTO counters VALUES ('a', 10);
            INSERT INTO counters VALUES ('b', 20);
            UPDATE counters SET val = val + 5 WHERE name = 'a';
            DELETE FROM counters WHERE name = 'b';
        """,
        )

        result = run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_duckdb(
            tmp_path / "test.duckdb",
            "SELECT name, val FROM counters",
        )
        assert rows == [("a", 15)]


# ---------------------------------------------------------------------------
# Test: substitution variables (SUB metacommand)
# ---------------------------------------------------------------------------


class TestSubstitutionVariables:
    def test_sub_variable_in_insert(self, tmp_path):
        """Define a SUB variable and use it in a SQL INSERT."""
        _write_conf(tmp_path)
        script = write_script(
            tmp_path,
            """\
            CREATE TABLE greetings (msg TEXT);

            -- !x! SUB myvar Hello World
            INSERT INTO greetings (msg) VALUES ('!!myvar!!');
        """,
        )

        result = run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_duckdb(
            tmp_path / "test.duckdb",
            "SELECT msg FROM greetings",
        )
        assert len(rows) == 1
        assert rows[0][0] == "Hello World"

    def test_sub_variable_in_table_name(self, tmp_path):
        """Use a SUB variable as part of a table name."""
        _write_conf(tmp_path)
        script = write_script(
            tmp_path,
            """\
            -- !x! SUB tblname mytable
            CREATE TABLE !!tblname!! (id INTEGER);
            INSERT INTO !!tblname!! VALUES (42);
        """,
        )

        result = run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_duckdb(tmp_path / "test.duckdb", "SELECT id FROM mytable")
        assert rows == [(42,)]


# ---------------------------------------------------------------------------
# Test: EXPORT to CSV
# ---------------------------------------------------------------------------


class TestExportCSV:
    def test_export_query_to_csv(self, tmp_path):
        """Run a SELECT and export results to a CSV file, then verify contents."""
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

        result = run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        assert csv_path.exists(), "CSV file was not created"
        with open(csv_path, newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)

        assert rows[0] == ["id", "label"]
        assert len(rows) == 4  # header + 3 data rows
        assert rows[1] == ["1", "alpha"]
        assert rows[2] == ["2", "beta"]
        assert rows[3] == ["3", "gamma"]


# ---------------------------------------------------------------------------
# Test: IMPORT from CSV
# ---------------------------------------------------------------------------


class TestImportCSV:
    def test_import_csv_into_table(self, tmp_path):
        """Import a CSV file into a table and verify row counts."""
        _write_conf(tmp_path)

        csv_path = tmp_path / "data.csv"
        csv_path.write_text("id,name,score\n1,Alice,95\n2,Bob,87\n3,Carol,92\n")

        script = write_script(
            tmp_path,
            f"""\
            CREATE TABLE students (id INTEGER, name TEXT, score INTEGER);

            -- !x! IMPORT TO students FROM {csv_path}
        """,
        )

        result = run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_duckdb(
            tmp_path / "test.duckdb",
            "SELECT id, name, score FROM students ORDER BY id",
        )
        assert len(rows) == 3
        assert rows[0] == (1, "Alice", 95)
        assert rows[1] == (2, "Bob", 87)
        assert rows[2] == (3, "Carol", 92)


# ---------------------------------------------------------------------------
# Test: conditional execution (IF / ENDIF)
# ---------------------------------------------------------------------------


class TestConditionalExecution:
    def test_if_true_branch_executes(self, tmp_path):
        """IF condition is true: the block inside executes."""
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

        result = run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_duckdb(
            tmp_path / "test.duckdb",
            "SELECT branch FROM results",
        )
        assert rows == [("true_branch",)]

    def test_if_false_branch_skipped(self, tmp_path):
        """IF condition is false: the block is skipped."""
        _write_conf(tmp_path)
        script = write_script(
            tmp_path,
            """\
            CREATE TABLE results (branch TEXT);

            -- !x! SUB testval 0
            -- !x! IF (EQUALS(!!testval!!, 1))
            INSERT INTO results VALUES ('should_not_appear');
            -- !x! ENDIF
        """,
        )

        result = run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_duckdb(
            tmp_path / "test.duckdb",
            "SELECT branch FROM results",
        )
        assert rows == []

    def test_if_else(self, tmp_path):
        """IF/ELSE: the ELSE branch executes when the condition is false."""
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

        result = run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_duckdb(
            tmp_path / "test.duckdb",
            "SELECT branch FROM results",
        )
        assert rows == [("else_branch",)]

    def test_nested_if(self, tmp_path):
        """Nested IF blocks execute correctly."""
        _write_conf(tmp_path)
        script = write_script(
            tmp_path,
            """\
            CREATE TABLE results (val TEXT);

            -- !x! SUB outer 1
            -- !x! SUB inner 1
            -- !x! IF (EQUALS(!!outer!!, 1))
            -- !x! IF (EQUALS(!!inner!!, 1))
            INSERT INTO results VALUES ('both_true');
            -- !x! ENDIF
            -- !x! ENDIF
        """,
        )

        result = run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_duckdb(
            tmp_path / "test.duckdb",
            "SELECT val FROM results",
        )
        assert rows == [("both_true",)]


# ---------------------------------------------------------------------------
# Test: WRITE metacommand
# ---------------------------------------------------------------------------


class TestWriteMetacommand:
    def test_write_to_stdout(self, tmp_path):
        """WRITE metacommand without a TO clause prints to stdout."""
        _write_conf(tmp_path)
        script = write_script(
            tmp_path,
            """\
            -- !x! WRITE "Hello from execsql"
        """,
        )

        result = run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Hello from execsql" in result.stdout


# ---------------------------------------------------------------------------
# Test: end-to-end round-trip (create, export, re-import)
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_create_export_reimport(self, tmp_path):
        """Create a table, export to CSV, drop table, re-import, and verify."""
        _write_conf(tmp_path)
        csv_path = tmp_path / "roundtrip.csv"
        script = write_script(
            tmp_path,
            f"""\
            CREATE TABLE original (id INTEGER, color TEXT);
            INSERT INTO original VALUES (1, 'red');
            INSERT INTO original VALUES (2, 'green');
            INSERT INTO original VALUES (3, 'blue');

            -- !x! EXPORT QUERY << SELECT id, color FROM original ORDER BY id; >> TO {csv_path} AS CSV

            DROP TABLE original;
            CREATE TABLE reimported (id INTEGER, color TEXT);

            -- !x! IMPORT TO reimported FROM {csv_path}
        """,
        )

        result = run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_duckdb(
            tmp_path / "test.duckdb",
            "SELECT id, color FROM reimported ORDER BY id",
        )
        assert len(rows) == 3
        assert rows[0] == (1, "red")
        assert rows[1] == (2, "green")
        assert rows[2] == (3, "blue")


# ---------------------------------------------------------------------------
# DuckDB-specific tests (features not applicable to SQLite)
# ---------------------------------------------------------------------------


class TestDuckDBSpecific:
    def test_create_and_query_view(self, tmp_path):
        """DuckDB views are queryable through execsql."""
        _write_conf(tmp_path)
        script = write_script(
            tmp_path,
            """\
            CREATE TABLE base (id INTEGER, val DOUBLE);
            INSERT INTO base VALUES (1, 10.5);
            INSERT INTO base VALUES (2, 20.3);

            CREATE VIEW doubled AS SELECT id, val * 2 AS val2 FROM base;
        """,
        )

        result = run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_duckdb(
            tmp_path / "test.duckdb",
            "SELECT id, val2 FROM doubled ORDER BY id",
        )
        assert len(rows) == 2
        assert rows[0] == (1, 21.0)
        assert rows[1] == (2, 40.6)

    def test_schema_creation(self, tmp_path):
        """DuckDB supports schemas beyond the default 'main'."""
        _write_conf(tmp_path)
        script = write_script(
            tmp_path,
            """\
            CREATE SCHEMA staging;
            CREATE TABLE staging.events (id INTEGER, name TEXT);
            INSERT INTO staging.events VALUES (1, 'click');
        """,
        )

        result = run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_duckdb(
            tmp_path / "test.duckdb",
            "SELECT id, name FROM staging.events",
        )
        assert rows == [(1, "click")]

    def test_duckdb_native_types(self, tmp_path):
        """DuckDB supports types beyond typical SQLite (DATE, TIMESTAMP, LIST)."""
        _write_conf(tmp_path)
        script = write_script(
            tmp_path,
            """\
            CREATE TABLE typed (
                d DATE,
                ts TIMESTAMP,
                flag BOOLEAN
            );
            INSERT INTO typed VALUES ('2026-01-15', '2026-01-15 10:30:00', true);
            INSERT INTO typed VALUES ('2026-06-01', '2026-06-01 14:00:00', false);
        """,
        )

        result = run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        rows = _query_duckdb(
            tmp_path / "test.duckdb",
            "SELECT flag FROM typed ORDER BY d",
        )
        assert rows[0][0] is True
        assert rows[1][0] is False
