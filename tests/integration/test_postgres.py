"""Integration tests that run SQL scripts through the full execsql pipeline using PostgreSQL.

Mirrors the SQLite integration tests in test_sqlite.py but uses PostgreSQL as
the backend (db_type = p).  Each test writes a minimal execsql.conf, creates a
.sql script with metacommands, invokes the CLI via subprocess, and asserts
outcomes (tables created, data inserted, files exported, etc.).

The entire module is skipped when:
  - psycopg (psycopg3) is not installed, OR
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
# Module-level skip: psycopg (psycopg3) availability + server reachability
# ---------------------------------------------------------------------------

psycopg = pytest.importorskip("psycopg", reason="psycopg (psycopg3) package required")

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
        conn = psycopg.connect(**_PG_CONNECT_KWARGS)
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

    cmd = [sys.executable, "-m", "execsql", "run", "--dsn", _PG_DSN, str(script_path)]
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
    conn = psycopg.connect(**_PG_CONNECT_KWARGS)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


def _exec_pg(sql: str, params=None):
    """Execute a non-SELECT statement against the test PostgreSQL database."""
    conn = psycopg.connect(**_PG_CONNECT_KWARGS)
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

    # Issue #54: COPY's CSV format treats `"` as a quote character unless told
    # otherwise, so a file read with no quote character lost its double quotes.

    def test_quote_none_keeps_double_quotes(self, tmp_path):
        """The reproduction from #54: IMPORT TO REPLACEMENT ... WITH QUOTE NONE."""
        _exec_pg("DROP TABLE IF EXISTS quote_repro")
        _write_conf(tmp_path)
        (tmp_path / "names.txt").write_text('name\nWell "A" 12\nplain\n')
        script = write_script(
            tmp_path,
            """\
            -- !x! IMPORT TO REPLACEMENT public.quote_repro FROM "names.txt" WITH QUOTE NONE DELIMITER TAB
            """,
        )
        result = _run_execsql_pg(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert sorted(_query_pg("SELECT name FROM quote_repro")) == [('Well "A" 12',), ("plain",)]
        _exec_pg("DROP TABLE IF EXISTS quote_repro")

    def test_quote_none_into_existing_table(self, tmp_path):
        _exec_pg("DROP TABLE IF EXISTS quote_existing")
        _write_conf(tmp_path)
        (tmp_path / "files.txt").write_text('id\tpath\n1\t"quoted".sql\n2\ta, b.sql\n')
        script = write_script(
            tmp_path,
            """\
            CREATE TABLE quote_existing (id INTEGER, path TEXT);
            -- !x! IMPORT TO quote_existing FROM "files.txt" WITH QUOTE NONE DELIMITER TAB
            """,
        )
        result = _run_execsql_pg(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert _query_pg("SELECT id, path FROM quote_existing ORDER BY id") == [(1, '"quoted".sql'), (2, "a, b.sql")]
        _exec_pg("DROP TABLE IF EXISTS quote_existing")

    def test_detected_no_quote_keeps_double_quotes(self, tmp_path):
        """No QUOTE clause: a " inside an unquoted field means the file has no quote character."""
        _exec_pg("DROP TABLE IF EXISTS quote_detected")
        _write_conf(tmp_path)
        (tmp_path / "sizes.txt").write_text('id\tsize\n1\t12" pipe\n2\t3 ft\n')
        script = write_script(
            tmp_path,
            """\
            CREATE TABLE quote_detected (id INTEGER, size TEXT);
            -- !x! IMPORT TO quote_detected FROM "sizes.txt"
            """,
        )
        result = _run_execsql_pg(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert _query_pg("SELECT id, size FROM quote_detected ORDER BY id") == [(1, '12" pipe'), (2, "3 ft")]
        _exec_pg("DROP TABLE IF EXISTS quote_detected")

    def test_detected_backslash_escape_is_honored(self, tmp_path):
        """COPY was not told about a detected escape character, so `\\"` became `\\`."""
        _exec_pg("DROP TABLE IF EXISTS quote_escaped")
        _write_conf(tmp_path)
        (tmp_path / "escaped.csv").write_text('id,name\n1,"Well \\"A\\" 12"\n2,"plain"\n')
        script = write_script(
            tmp_path,
            """\
            CREATE TABLE quote_escaped (id INTEGER, name TEXT);
            -- !x! IMPORT TO quote_escaped FROM "escaped.csv"
            """,
        )
        result = _run_execsql_pg(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert _query_pg("SELECT id, name FROM quote_escaped ORDER BY id") == [(1, 'Well "A" 12'), (2, "plain")]
        _exec_pg("DROP TABLE IF EXISTS quote_escaped")


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


# ---------------------------------------------------------------------------
# Regression: psycopg3 cached-plan / auto-prepared statements
#
# psycopg3 promotes a query to a server-side prepared statement after the same
# query text runs prepare_threshold times (default 5).  Re-EXPORTing a view that
# the script drops/recreates with a different result type used to raise
# "FeatureNotSupported: cached plan must not change result type".  The adapter
# now connects with prepare_threshold=None; this exercises the full pipeline to
# prove the fix end-to-end.  See CHANGELOG 2.21.1.
# ---------------------------------------------------------------------------


class TestCachedPlanRegression:
    def test_repeated_export_after_view_result_type_change(self, tmp_path):
        """EXPORT the same view past the prepare threshold, then recreate it with
        a different column type and EXPORT again — must not error."""
        _exec_pg("DROP VIEW IF EXISTS val_summ")
        _exec_pg("DROP TABLE IF EXISTS val_src")
        _write_conf(tmp_path)
        out = tmp_path / "summ.txt"

        # Six exports of identical query text cross psycopg3's default
        # prepare_threshold (5); the view is then recreated returning a TEXT
        # column instead of an INTEGER one and exported again.
        first_exports = "\n".join(f"-- !x! EXPORT val_summ TO {out} AS TXT" for _ in range(6))
        second_exports = "\n".join(f"-- !x! EXPORT val_summ TO {out} AS TXT" for _ in range(6))
        script = write_script(
            tmp_path,
            f"""\
            CREATE TABLE val_src (id INTEGER, name TEXT);
            INSERT INTO val_src VALUES (1, 'alpha');

            CREATE VIEW val_summ AS SELECT id AS c FROM val_src;
            {first_exports}

            DROP VIEW val_summ;
            CREATE VIEW val_summ AS SELECT name AS c FROM val_src;
            {second_exports}
            """,
        )

        result = _run_execsql_pg(tmp_path, script)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "cached plan must not change result type" not in result.stderr
        # The final export reflects the recreated (TEXT) view.
        assert "alpha" in out.read_text()

        _exec_pg("DROP VIEW IF EXISTS val_summ")
        _exec_pg("DROP TABLE IF EXISTS val_src")


# ---------------------------------------------------------------------------
# Test: PG_UPSERT against the real pg-upsert package
# ---------------------------------------------------------------------------


@pytest.fixture
def upsert_schemas():
    """Base table ``ups_base.books`` (title varchar(5) NOT NULL) holding id 1,
    and an unconstrained staging copy ``ups_stg.books``.  Dropped afterwards."""
    pytest.importorskip("pg_upsert", reason="pg-upsert package required (execsql2[upsert])")
    _exec_pg("DROP SCHEMA IF EXISTS ups_stg CASCADE")
    _exec_pg("DROP SCHEMA IF EXISTS ups_base CASCADE")
    _exec_pg("CREATE SCHEMA ups_base")
    _exec_pg("CREATE SCHEMA ups_stg")
    _exec_pg("CREATE TABLE ups_base.books (id INTEGER PRIMARY KEY, title VARCHAR(5) NOT NULL)")
    _exec_pg("INSERT INTO ups_base.books VALUES (1, 'old')")
    _exec_pg("CREATE TABLE ups_stg.books (id INTEGER, title TEXT)")
    yield
    _exec_pg("DROP SCHEMA IF EXISTS ups_stg CASCADE")
    _exec_pg("DROP SCHEMA IF EXISTS ups_base CASCADE")


def _upsert_outcomes(tmp_path, metacommands: str) -> dict[str, str]:
    """Run *metacommands* and return the ``key=value`` lines they WRITE to out.txt."""
    _write_conf(tmp_path)
    out = tmp_path / "out.txt"
    script = write_script(tmp_path, metacommands.replace("OUT", str(out)))
    result = _run_execsql_pg(tmp_path, script, timeout=60)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    return dict(line.split("=", 1) for line in out.read_text().splitlines())


class TestPgUpsert:
    def test_qa_follows_method(self, tmp_path, upsert_schemas):
        """A NULL title on a new row fails QA for upsert, but update never writes that row."""
        _exec_pg("INSERT INTO ups_stg.books VALUES (1, 'new'), (2, NULL)")
        outcomes = _upsert_outcomes(
            tmp_path,
            """\
            -- !x! PG_UPSERT QA FROM ups_stg TO ups_base TABLES books
            -- !x! WRITE "upsert=!!$PG_UPSERT_QA_PASSED!!" TO OUT
            -- !x! PG_UPSERT QA FROM ups_stg TO ups_base TABLES books METHOD update
            -- !x! WRITE "update=!!$PG_UPSERT_QA_PASSED!!" TO OUT
            """,
        )
        assert outcomes == {"upsert": "FALSE", "update": "TRUE"}

    def test_update_loads_only_existing_rows(self, tmp_path, upsert_schemas):
        _exec_pg("INSERT INTO ups_stg.books VALUES (1, 'new'), (2, NULL)")
        outcomes = _upsert_outcomes(
            tmp_path,
            """\
            -- !x! PG_UPSERT FROM ups_stg TO ups_base TABLES books METHOD update COMMIT
            -- !x! WRITE "committed=!!$PG_UPSERT_COMMITTED!!" TO OUT
            -- !x! WRITE "updated=!!$PG_UPSERT_ROWS_UPDATED!!" TO OUT
            -- !x! WRITE "inserted=!!$PG_UPSERT_ROWS_INSERTED!!" TO OUT
            """,
        )
        assert outcomes == {"committed": "TRUE", "updated": "1", "inserted": "0"}
        assert _query_pg("SELECT id, title FROM ups_base.books ORDER BY id") == [(1, "new")]

    def test_length_check_fails_qa_and_reaches_the_fix_sheet(self, tmp_path, upsert_schemas):
        _exec_pg("INSERT INTO ups_stg.books VALUES (1, 'toolong')")
        outcomes = _upsert_outcomes(
            tmp_path,
            """\
            -- !x! PG_UPSERT QA FROM ups_stg TO ups_base TABLES books EXPORT_FAILURES fixes
            -- !x! WRITE "passed=!!$PG_UPSERT_QA_PASSED!!" TO OUT
            """,
        )
        assert outcomes == {"passed": "FALSE"}
        fix_sheet = "".join(p.read_text() for p in (tmp_path / "fixes").glob("*.csv"))
        assert "toolong" in fix_sheet
        assert "length" in fix_sheet

    def test_check_warns_on_missing_required_column_for_update(self, tmp_path, upsert_schemas):
        """A missing NOT NULL column blocks an upsert but is only a warning for update."""
        _exec_pg("ALTER TABLE ups_stg.books DROP COLUMN title")
        outcomes = _upsert_outcomes(
            tmp_path,
            """\
            -- !x! PG_UPSERT CHECK FROM ups_stg TO ups_base TABLES books
            -- !x! WRITE "upsert=!!$PG_UPSERT_QA_PASSED!!" TO OUT
            -- !x! PG_UPSERT CHECK FROM ups_stg TO ups_base TABLES books METHOD update
            -- !x! WRITE "update=!!$PG_UPSERT_QA_PASSED!!" TO OUT
            -- !x! WRITE "warnings=!!$PG_UPSERT_QA_WARNINGS!!" TO OUT
            """,
        )
        assert outcomes == {"upsert": "FALSE", "update": "TRUE", "warnings": "books"}


def test_copy_names_its_source_the_way_the_database_resolves_it(tmp_path):
    """``COPY Orders_Mixed ...`` reads the folded ``orders_mixed``; an existence check in another case must not refuse it."""
    from execsql import run

    run(sql="drop table if exists orders_mixed;\n", dsn=_PG_DSN)
    try:
        result = run(
            sql=(
                "create table orders_mixed (id integer);\n"
                "insert into orders_mixed values (1);\n"
                f"-- !x! CONNECT TO SQLITE(FILE={tmp_path / 'dst.db'}, NEW) AS dst\n"
                "-- !x! COPY Orders_Mixed FROM initial TO NEW copied IN dst\n"
            ),
            dsn=_PG_DSN,
        )
        assert result.success, result.errors
    finally:
        run(sql="drop table if exists orders_mixed;\n", dsn=_PG_DSN)


def test_import_to_new_refuses_an_existing_table(tmp_path):
    from execsql import run

    csv = tmp_path / "q.csv"
    csv.write_text("a,b\n1,2\n")
    run(sql="drop table if exists new_target;\n", dsn=_PG_DSN)
    try:
        result = run(
            sql=f"create table new_target (keep text);\n-- !x! IMPORT TO NEW new_target FROM {csv}\n",
            dsn=_PG_DSN,
        )
        assert not result.success
        assert "Table new_target already exists" in result.errors[0].message
    finally:
        run(sql="drop table if exists new_target;\n", dsn=_PG_DSN)
