"""Integration tests that run SQL scripts through the full execsql pipeline using SQLite.

Each test writes a minimal execsql.conf, creates a .sql script with metacommands,
invokes the CLI via subprocess, and asserts outcomes (tables created, data inserted,
files exported, etc.).
"""

from __future__ import annotations

import csv
import json
import sqlite3
import subprocess
import sys
import textwrap


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_conf(tmp_path, db_filename="test.db", extra=""):
    """Write a minimal execsql.conf for SQLite into *tmp_path*."""
    conf = tmp_path / "execsql.conf"
    conf.write_text(
        textwrap.dedent(f"""\
        [connect]
        db_type = l
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


def _write_script(tmp_path, sql_text, name="test_script.sql"):
    """Write a .sql script file into *tmp_path*."""
    script = tmp_path / name
    script.write_text(textwrap.dedent(sql_text))
    return script


def _run_execsql(tmp_path, script_path, extra_args=None, timeout=30):
    """Run execsql on the given script via subprocess.

    Returns the completed process. The working directory is set to *tmp_path*
    so that execsql.conf is picked up automatically.
    """
    cmd = [sys.executable, "-m", "execsql", str(script_path)]
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(
        cmd,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result


# ---------------------------------------------------------------------------
# Test: basic SQL execution (CREATE TABLE, INSERT, SELECT)
# ---------------------------------------------------------------------------


class TestBasicSQLExecution:
    def test_create_table_and_insert(self, tmp_path):
        """CREATE TABLE + INSERT via execsql, then verify rows in the DB."""
        _write_conf(tmp_path)
        script = _write_script(
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

        result = _run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        db_path = tmp_path / "test.db"
        assert db_path.exists()

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT id, name FROM fruits ORDER BY id").fetchall()
        conn.close()

        assert len(rows) == 3
        assert rows[0] == (1, "apple")
        assert rows[1] == (2, "banana")
        assert rows[2] == (3, "cherry")

    def test_multiple_statements(self, tmp_path):
        """Run multiple DDL/DML statements in sequence."""
        _write_conf(tmp_path)
        script = _write_script(
            tmp_path,
            """\
            CREATE TABLE counters (name TEXT, val INTEGER);
            INSERT INTO counters VALUES ('a', 10);
            INSERT INTO counters VALUES ('b', 20);
            UPDATE counters SET val = val + 5 WHERE name = 'a';
            DELETE FROM counters WHERE name = 'b';
        """,
        )

        result = _run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute("SELECT name, val FROM counters").fetchall()
        conn.close()

        assert rows == [("a", 15)]


# ---------------------------------------------------------------------------
# Test: substitution variables (SUB metacommand)
# ---------------------------------------------------------------------------


class TestSubstitutionVariables:
    def test_sub_variable_in_insert(self, tmp_path):
        """Define a SUB variable and use it in a SQL INSERT."""
        _write_conf(tmp_path)
        script = _write_script(
            tmp_path,
            """\
            CREATE TABLE greetings (msg TEXT);

            -- !x! SUB myvar Hello World
            INSERT INTO greetings (msg) VALUES ('!!myvar!!');
        """,
        )

        result = _run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute("SELECT msg FROM greetings").fetchall()
        conn.close()

        assert len(rows) == 1
        assert rows[0][0] == "Hello World"

    def test_sub_variable_in_table_name(self, tmp_path):
        """Use a SUB variable as part of a table name."""
        _write_conf(tmp_path)
        script = _write_script(
            tmp_path,
            """\
            -- !x! SUB tblname mytable
            CREATE TABLE !!tblname!! (id INTEGER);
            INSERT INTO !!tblname!! VALUES (42);
        """,
        )

        result = _run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute("SELECT id FROM mytable").fetchall()
        conn.close()

        assert rows == [(42,)]


# ---------------------------------------------------------------------------
# Test: EXPORT to CSV
# ---------------------------------------------------------------------------


class TestExportCSV:
    def test_export_query_to_csv(self, tmp_path):
        """Run a SELECT and export results to a CSV file, then verify contents."""
        _write_conf(tmp_path)
        csv_path = tmp_path / "output.csv"
        script = _write_script(
            tmp_path,
            f"""\
            CREATE TABLE items (id INTEGER, label TEXT);
            INSERT INTO items VALUES (1, 'alpha');
            INSERT INTO items VALUES (2, 'beta');
            INSERT INTO items VALUES (3, 'gamma');

            -- !x! EXPORT QUERY << SELECT id, label FROM items ORDER BY id; >> TO {csv_path} AS CSV
        """,
        )

        result = _run_execsql(tmp_path, script)
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


# ---------------------------------------------------------------------------
# Test: IMPORT from CSV
# ---------------------------------------------------------------------------


class TestImportCSV:
    def test_import_csv_into_table(self, tmp_path):
        """Import a CSV file into a table and verify row counts."""
        _write_conf(tmp_path)

        # Write the CSV file to import
        csv_path = tmp_path / "data.csv"
        csv_path.write_text("id,name,score\n1,Alice,95\n2,Bob,87\n3,Carol,92\n")

        script = _write_script(
            tmp_path,
            f"""\
            CREATE TABLE students (id INTEGER, name TEXT, score INTEGER);

            -- !x! IMPORT TO students FROM {csv_path}
        """,
        )

        result = _run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute("SELECT id, name, score FROM students ORDER BY id").fetchall()
        conn.close()

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
        script = _write_script(
            tmp_path,
            """\
            CREATE TABLE results (branch TEXT);

            -- !x! SUB testval 1
            -- !x! IF (EQUALS(!!testval!!, 1))
            INSERT INTO results VALUES ('true_branch');
            -- !x! ENDIF
        """,
        )

        result = _run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute("SELECT branch FROM results").fetchall()
        conn.close()

        assert rows == [("true_branch",)]

    def test_if_false_branch_skipped(self, tmp_path):
        """IF condition is false: the block is skipped."""
        _write_conf(tmp_path)
        script = _write_script(
            tmp_path,
            """\
            CREATE TABLE results (branch TEXT);

            -- !x! SUB testval 0
            -- !x! IF (EQUALS(!!testval!!, 1))
            INSERT INTO results VALUES ('should_not_appear');
            -- !x! ENDIF
        """,
        )

        result = _run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute("SELECT branch FROM results").fetchall()
        conn.close()

        assert rows == []

    def test_if_else(self, tmp_path):
        """IF/ELSE: the ELSE branch executes when the condition is false."""
        _write_conf(tmp_path)
        script = _write_script(
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

        result = _run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute("SELECT branch FROM results").fetchall()
        conn.close()

        assert rows == [("else_branch",)]

    def test_nested_if(self, tmp_path):
        """Nested IF blocks execute correctly."""
        _write_conf(tmp_path)
        script = _write_script(
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

        result = _run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute("SELECT val FROM results").fetchall()
        conn.close()

        assert rows == [("both_true",)]


# ---------------------------------------------------------------------------
# Test: WRITE metacommand
# ---------------------------------------------------------------------------


class TestWriteMetacommand:
    def test_write_to_stdout(self, tmp_path):
        """WRITE metacommand without a TO clause prints to stdout."""
        _write_conf(tmp_path)
        script = _write_script(
            tmp_path,
            """\
            -- !x! WRITE "Hello from execsql"
        """,
        )

        result = _run_execsql(tmp_path, script)
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
        script = _write_script(
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

        result = _run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute("SELECT id, color FROM reimported ORDER BY id").fetchall()
        conn.close()

        assert len(rows) == 3
        assert rows[0] == (1, "red")
        assert rows[1] == (2, "green")
        assert rows[2] == (3, "blue")


# ---------------------------------------------------------------------------
# Test: export to JSON
# ---------------------------------------------------------------------------


class TestExportJSON:
    def test_export_query_to_json(self, tmp_path):
        """Export query results to a JSON file."""
        _write_conf(tmp_path)
        out = tmp_path / "output.json"
        script = _write_script(
            tmp_path,
            f"""\
            CREATE TABLE items (id INTEGER, label TEXT);
            INSERT INTO items VALUES (1, 'alpha');
            INSERT INTO items VALUES (2, 'beta');

            -- !x! EXPORT QUERY << SELECT id, label FROM items ORDER BY id; >> TO {out} AS JSON
        """,
        )

        result = _run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert out.exists()

        data = json.loads(out.read_text())
        assert len(data) == 2
        assert data[0]["id"] == 1
        assert data[0]["label"] == "alpha"
        assert data[1]["id"] == 2
        assert data[1]["label"] == "beta"


# ---------------------------------------------------------------------------
# Test: export to HTML
# ---------------------------------------------------------------------------


class TestExportHTML:
    def test_export_query_to_html(self, tmp_path):
        """Export query results to an HTML file and verify it contains a table."""
        _write_conf(tmp_path)
        out = tmp_path / "output.html"
        script = _write_script(
            tmp_path,
            f"""\
            CREATE TABLE items (id INTEGER, label TEXT);
            INSERT INTO items VALUES (1, 'alpha');
            INSERT INTO items VALUES (2, 'beta');

            -- !x! EXPORT QUERY << SELECT id, label FROM items ORDER BY id; >> TO {out} AS HTML
        """,
        )

        result = _run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert out.exists()

        content = out.read_text()
        assert "<table" in content.lower()
        assert "alpha" in content
        assert "beta" in content


# ---------------------------------------------------------------------------
# Test: export to LaTeX
# ---------------------------------------------------------------------------


class TestExportLaTeX:
    def test_export_query_to_latex(self, tmp_path):
        """Export query results to a LaTeX file."""
        _write_conf(tmp_path)
        out = tmp_path / "output.tex"
        script = _write_script(
            tmp_path,
            f"""\
            CREATE TABLE items (id INTEGER, label TEXT);
            INSERT INTO items VALUES (1, 'alpha');
            INSERT INTO items VALUES (2, 'beta');

            -- !x! EXPORT QUERY << SELECT id, label FROM items ORDER BY id; >> TO {out} AS LATEX
        """,
        )

        result = _run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert out.exists()

        content = out.read_text()
        assert "tabular" in content or "begin" in content
        assert "alpha" in content
        assert "beta" in content


# ---------------------------------------------------------------------------
# Test: export to TSV
# ---------------------------------------------------------------------------


class TestExportTSV:
    def test_export_query_to_tsv(self, tmp_path):
        """Export query results to a TSV file."""
        _write_conf(tmp_path)
        out = tmp_path / "output.tsv"
        script = _write_script(
            tmp_path,
            f"""\
            CREATE TABLE items (id INTEGER, label TEXT);
            INSERT INTO items VALUES (1, 'alpha');
            INSERT INTO items VALUES (2, 'beta');

            -- !x! EXPORT QUERY << SELECT id, label FROM items ORDER BY id; >> TO {out} AS TSV
        """,
        )

        result = _run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert out.exists()

        lines = out.read_text().strip().splitlines()
        assert len(lines) == 3  # header + 2 data
        assert "id" in lines[0] and "label" in lines[0]
        assert "alpha" in lines[1]
        assert "beta" in lines[2]


# ---------------------------------------------------------------------------
# Test: DDL — views, indexes, multiple tables
# ---------------------------------------------------------------------------


class TestDDLOperations:
    def test_create_view(self, tmp_path):
        """Create a view and query through it."""
        _write_conf(tmp_path)
        script = _write_script(
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

        result = _run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute("SELECT name FROM eng_employees ORDER BY name").fetchall()
        conn.close()

        assert rows == [("Alice",), ("Carol",)]

    def test_create_index(self, tmp_path):
        """Create an index on a table."""
        _write_conf(tmp_path)
        script = _write_script(
            tmp_path,
            """\
            CREATE TABLE logs (id INTEGER PRIMARY KEY, ts TEXT, msg TEXT);
            CREATE INDEX idx_logs_ts ON logs(ts);
            INSERT INTO logs VALUES (1, '2025-01-01', 'start');
        """,
        )

        result = _run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='logs'",
        ).fetchall()
        conn.close()

        index_names = [r[0] for r in indexes]
        assert "idx_logs_ts" in index_names

    def test_drop_and_recreate_table(self, tmp_path):
        """Drop a table and recreate it."""
        _write_conf(tmp_path)
        script = _write_script(
            tmp_path,
            """\
            CREATE TABLE tmp (val INTEGER);
            INSERT INTO tmp VALUES (1);
            DROP TABLE tmp;
            CREATE TABLE tmp (val TEXT);
            INSERT INTO tmp VALUES ('rebuilt');
        """,
        )

        result = _run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute("SELECT val FROM tmp").fetchall()
        conn.close()

        assert rows == [("rebuilt",)]


# ---------------------------------------------------------------------------
# Test: WRITE TO file metacommand
# ---------------------------------------------------------------------------


class TestWriteToFile:
    def test_write_to_file(self, tmp_path):
        """WRITE TO <file> creates an output file with the expected text."""
        _write_conf(tmp_path)
        out = tmp_path / "message.txt"
        script = _write_script(
            tmp_path,
            f"""\
            -- !x! WRITE "Hello from execsql" TO {out}
        """,
        )

        result = _run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert out.exists()

        content = out.read_text()
        assert "Hello from execsql" in content


# ---------------------------------------------------------------------------
# Test: WRITE with substitution variables
# ---------------------------------------------------------------------------


class TestWriteWithSubVars:
    def test_write_with_system_vars(self, tmp_path):
        """WRITE can interpolate system substitution variables."""
        _write_conf(tmp_path)
        out = tmp_path / "info.txt"
        script = _write_script(
            tmp_path,
            f"""\
            -- !x! WRITE "OS=!!$OS!!" TO {out}
        """,
        )

        result = _run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert out.exists()

        content = out.read_text()
        assert "OS=" in content
        # Should contain an actual OS value, not the raw variable
        assert "!!$OS!!" not in content


# ---------------------------------------------------------------------------
# Test: CONFIG metacommand
# ---------------------------------------------------------------------------


class TestConfigMetacommand:
    def test_config_make_export_dirs(self, tmp_path):
        """CONFIG MAKE_EXPORT_DIRS creates intermediate directories for EXPORT."""
        _write_conf(tmp_path)
        out = tmp_path / "subdir" / "deep" / "output.csv"
        script = _write_script(
            tmp_path,
            f"""\
            -- !x! CONFIG MAKE_EXPORT_DIRS Yes
            CREATE TABLE items (id INTEGER);
            INSERT INTO items VALUES (1);

            -- !x! EXPORT QUERY << SELECT id FROM items; >> TO {out} AS CSV
        """,
        )

        result = _run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert out.exists()


# ---------------------------------------------------------------------------
# Test: error handling — bad SQL
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_bad_sql_reports_error(self, tmp_path):
        """A SQL syntax error causes a non-zero exit or error output."""
        _write_conf(tmp_path)
        script = _write_script(
            tmp_path,
            """\
            CREATE TABLE good (id INTEGER);
            INSERT INTO good VALUES (1);
            SELECTT BAD SYNTAX HERE;
        """,
        )

        result = _run_execsql(tmp_path, script)
        # Should fail (non-zero exit) or produce error output
        assert result.returncode != 0 or "error" in result.stderr.lower()

    def test_halt_on_error(self, tmp_path):
        """HALT ON ERROR stops execution at the first error."""
        _write_conf(tmp_path)
        script = _write_script(
            tmp_path,
            """\
            -- !x! HALT ON ERROR
            CREATE TABLE t1 (id INTEGER);
            INSERT INTO nonexistent_table VALUES (1);
            CREATE TABLE t2 (id INTEGER);
        """,
        )

        result = _run_execsql(tmp_path, script)
        assert result.returncode != 0

        # t2 should NOT have been created because HALT ON ERROR
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='t2'",
        ).fetchall()
        conn.close()

        assert len(tables) == 0, "t2 should not exist — HALT ON ERROR should have stopped execution"


# ---------------------------------------------------------------------------
# Test: inline command (-c flag)
# ---------------------------------------------------------------------------


class TestInlineCommand:
    def test_inline_create_and_insert(self, tmp_path):
        """The -c flag runs an inline script without a .sql file."""
        _write_conf(tmp_path)
        inline = "CREATE TABLE inline_test (val TEXT);\\nINSERT INTO inline_test VALUES ('hello');"

        result = subprocess.run(
            [sys.executable, "-m", "execsql", "-c", inline],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute("SELECT val FROM inline_test").fetchall()
        conn.close()

        assert rows == [("hello",)]


# ---------------------------------------------------------------------------
# Test: multiple exports in one script
# ---------------------------------------------------------------------------


class TestMultipleExports:
    def test_csv_and_json_exports(self, tmp_path):
        """A single script can produce both CSV and JSON exports."""
        _write_conf(tmp_path)
        csv_out = tmp_path / "out.csv"
        json_out = tmp_path / "out.json"
        script = _write_script(
            tmp_path,
            f"""\
            CREATE TABLE data (id INTEGER, val TEXT);
            INSERT INTO data VALUES (1, 'x');
            INSERT INTO data VALUES (2, 'y');

            -- !x! EXPORT QUERY << SELECT id, val FROM data ORDER BY id; >> TO {csv_out} AS CSV
            -- !x! EXPORT QUERY << SELECT id, val FROM data ORDER BY id; >> TO {json_out} AS JSON
        """,
        )

        result = _run_execsql(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        assert csv_out.exists()
        assert json_out.exists()

        rows = list(csv.reader(csv_out.open(newline="")))
        assert len(rows) == 3  # header + 2

        data = json.loads(json_out.read_text())
        assert len(data) == 2
