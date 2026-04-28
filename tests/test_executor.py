"""Integration tests for the AST-based executor.

Each test runs a self-verifying SQL script with the ``--ast`` flag against
a fresh SQLite database.  Scripts use ``ASSERT`` metacommands internally,
so a non-zero exit code means the executor produced incorrect results.

Tests also compare ``--ast`` output against the legacy engine to verify
behavioral equivalence.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXTURES = Path(__file__).parent / "scripts" / "fixtures"


def _run_ast(
    script_content: str,
    tmp_path: Path,
    *,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess:
    """Write *script_content* to a temp file and run it with ``--ast``."""
    script = tmp_path / "test.sql"
    script.write_text(script_content)
    db = tmp_path / "test.db"
    args = [
        sys.executable,
        "-m",
        "execsql",
        "--ast",
        str(script),
        str(db),
        "-t",
        "l",
        "-n",
    ]
    if extra_args:
        args.extend(extra_args)
    return subprocess.run(
        args,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
    )


def _run_legacy(script_content: str, tmp_path: Path) -> subprocess.CompletedProcess:
    """Write *script_content* to a temp file and run it with the legacy engine."""
    script = tmp_path / "test.sql"
    script.write_text(script_content)
    db = tmp_path / "test.db"
    return subprocess.run(
        [sys.executable, "-m", "execsql", str(script), str(db), "-t", "l", "-n"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
    )


def _query_db(tmp_path: Path, sql: str) -> list:
    """Run a SQL query against the test database and return rows."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Fixture scripts: run all .sql fixtures with --ast
# ---------------------------------------------------------------------------


_SQL_SCRIPTS = sorted(_FIXTURES.glob("*.sql"))


@pytest.mark.parametrize(
    "sql_script",
    _SQL_SCRIPTS,
    ids=[s.stem for s in _SQL_SCRIPTS],
)
def test_fixture_scripts_with_ast(tmp_path: Path, sql_script: Path) -> None:
    """Execute each self-verifying fixture with --ast and assert exit-code 0."""
    db = tmp_path / "test.db"
    result = subprocess.run(
        [sys.executable, "-m", "execsql", "--ast", str(sql_script), str(db), "-t", "l", "-n"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"Script {sql_script.name} failed with --ast (rc={result.returncode}).\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# SQL execution
# ---------------------------------------------------------------------------


class TestSqlExecution:
    def test_simple_select(self, tmp_path):
        result = _run_ast("CREATE TABLE t (x INT);\nINSERT INTO t VALUES (42);", tmp_path)
        assert result.returncode == 0
        rows = _query_db(tmp_path, "SELECT x FROM t")
        assert rows == [(42,)]

    def test_multi_statement(self, tmp_path):
        result = _run_ast(
            "CREATE TABLE t (a INT, b TEXT);\nINSERT INTO t VALUES (1, 'hello');\nINSERT INTO t VALUES (2, 'world');",
            tmp_path,
        )
        assert result.returncode == 0
        rows = _query_db(tmp_path, "SELECT count(*) FROM t")
        assert rows == [(2,)]


# ---------------------------------------------------------------------------
# Variable substitution
# ---------------------------------------------------------------------------


class TestVariableSubstitution:
    def test_sub_and_use(self, tmp_path):
        result = _run_ast(
            "-- !x! SUB tbl my_table\nCREATE TABLE !!tbl!! (id INT);\nINSERT INTO !!tbl!! VALUES (1);",
            tmp_path,
        )
        assert result.returncode == 0
        rows = _query_db(tmp_path, "SELECT id FROM my_table")
        assert rows == [(1,)]

    def test_sub_add(self, tmp_path):
        result = _run_ast(
            "-- !x! SUB counter 5\n"
            "-- !x! SUB_ADD counter 3\n"
            "CREATE TABLE t (val INT);\n"
            "INSERT INTO t VALUES (!!counter!!);",
            tmp_path,
        )
        assert result.returncode == 0
        rows = _query_db(tmp_path, "SELECT val FROM t")
        assert rows == [(8,)]


# ---------------------------------------------------------------------------
# IF / ELSE / ELSEIF
# ---------------------------------------------------------------------------


class TestIfBlock:
    def test_if_true(self, tmp_path):
        result = _run_ast(
            "CREATE TABLE t (x INT);\n-- !x! IF (TRUE)\nINSERT INTO t VALUES (1);\n-- !x! ENDIF",
            tmp_path,
        )
        assert result.returncode == 0
        assert _query_db(tmp_path, "SELECT count(*) FROM t") == [(1,)]

    def test_if_false_skips(self, tmp_path):
        result = _run_ast(
            "CREATE TABLE t (x INT);\n-- !x! IF (FALSE)\nINSERT INTO t VALUES (1);\n-- !x! ENDIF",
            tmp_path,
        )
        assert result.returncode == 0
        assert _query_db(tmp_path, "SELECT count(*) FROM t") == [(0,)]

    def test_if_else(self, tmp_path):
        result = _run_ast(
            "CREATE TABLE t (x INT);\n"
            "-- !x! IF (FALSE)\n"
            "INSERT INTO t VALUES (1);\n"
            "-- !x! ELSE\n"
            "INSERT INTO t VALUES (2);\n"
            "-- !x! ENDIF",
            tmp_path,
        )
        assert result.returncode == 0
        assert _query_db(tmp_path, "SELECT x FROM t") == [(2,)]

    def test_if_elseif(self, tmp_path):
        result = _run_ast(
            "-- !x! SUB tier gold\n"
            "CREATE TABLE t (val TEXT);\n"
            "-- !x! IF (EQUALS(!!tier!!, platinum))\n"
            "INSERT INTO t VALUES ('platinum');\n"
            "-- !x! ELSEIF (EQUALS(!!tier!!, gold))\n"
            "INSERT INTO t VALUES ('gold');\n"
            "-- !x! ELSE\n"
            "INSERT INTO t VALUES ('other');\n"
            "-- !x! ENDIF",
            tmp_path,
        )
        assert result.returncode == 0
        assert _query_db(tmp_path, "SELECT val FROM t") == [("gold",)]

    def test_andif(self, tmp_path):
        result = _run_ast(
            "-- !x! SUB a 1\n"
            "-- !x! SUB b 2\n"
            "CREATE TABLE t (x INT);\n"
            "-- !x! IF (EQUALS(!!a!!, 1))\n"
            "-- !x! ANDIF (EQUALS(!!b!!, 2))\n"
            "INSERT INTO t VALUES (1);\n"
            "-- !x! ENDIF\n"
            "-- !x! IF (EQUALS(!!a!!, 1))\n"
            "-- !x! ANDIF (EQUALS(!!b!!, 99))\n"
            "INSERT INTO t VALUES (2);\n"
            "-- !x! ENDIF",
            tmp_path,
        )
        assert result.returncode == 0
        assert _query_db(tmp_path, "SELECT x FROM t") == [(1,)]

    def test_orif(self, tmp_path):
        result = _run_ast(
            "-- !x! SUB x 0\n"
            "-- !x! SUB y 1\n"
            "CREATE TABLE t (x INT);\n"
            "-- !x! IF (EQUALS(!!x!!, 1))\n"
            "-- !x! ORIF (EQUALS(!!y!!, 1))\n"
            "INSERT INTO t VALUES (1);\n"
            "-- !x! ENDIF",
            tmp_path,
        )
        assert result.returncode == 0
        assert _query_db(tmp_path, "SELECT x FROM t") == [(1,)]

    def test_inline_if(self, tmp_path):
        result = _run_ast(
            "-- !x! SUB found no\n"
            "-- !x! IF (TRUE) { SUB found yes }\n"
            "CREATE TABLE t (val TEXT);\n"
            "INSERT INTO t VALUES ('!!found!!');",
            tmp_path,
        )
        assert result.returncode == 0
        assert _query_db(tmp_path, "SELECT val FROM t") == [("yes",)]


# ---------------------------------------------------------------------------
# LOOP
# ---------------------------------------------------------------------------


class TestLoop:
    def test_while_loop(self, tmp_path):
        result = _run_ast(
            "-- !x! SUB counter 0\n"
            "CREATE TABLE t (i INT);\n"
            "-- !x! LOOP WHILE (NOT IS_GTE(!{counter}!, 3))\n"
            "-- !x! SUB_ADD counter 1\n"
            "INSERT INTO t VALUES (!!counter!!);\n"
            "-- !x! END LOOP",
            tmp_path,
        )
        assert result.returncode == 0
        rows = _query_db(tmp_path, "SELECT i FROM t ORDER BY i")
        assert rows == [(1,), (2,), (3,)]

    def test_until_loop(self, tmp_path):
        result = _run_ast(
            "-- !x! SUB counter 0\n"
            "CREATE TABLE t (i INT);\n"
            "-- !x! LOOP UNTIL (EQUALS(!{counter}!, 3))\n"
            "-- !x! SUB_ADD counter 1\n"
            "INSERT INTO t VALUES (!!counter!!);\n"
            "-- !x! ENDLOOP",
            tmp_path,
        )
        assert result.returncode == 0
        rows = _query_db(tmp_path, "SELECT i FROM t ORDER BY i")
        assert rows == [(1,), (2,), (3,)]

    def test_loop_with_break(self, tmp_path):
        result = _run_ast(
            "-- !x! SUB counter 0\n"
            "CREATE TABLE t (i INT);\n"
            "-- !x! LOOP WHILE (TRUE)\n"
            "-- !x! SUB_ADD counter 1\n"
            "INSERT INTO t VALUES (!!counter!!);\n"
            "-- !x! IF (EQUALS(!!counter!!, 5))\n"
            "-- !x! BREAK\n"
            "-- !x! ENDIF\n"
            "-- !x! END LOOP",
            tmp_path,
        )
        assert result.returncode == 0
        rows = _query_db(tmp_path, "SELECT count(*) FROM t")
        assert rows == [(5,)]


# ---------------------------------------------------------------------------
# BATCH
# ---------------------------------------------------------------------------


class TestBatch:
    def test_batch_commits(self, tmp_path):
        result = _run_ast(
            "CREATE TABLE t (x INT);\n"
            "-- !x! BEGIN BATCH\n"
            "INSERT INTO t VALUES (1);\n"
            "INSERT INTO t VALUES (2);\n"
            "-- !x! END BATCH",
            tmp_path,
        )
        assert result.returncode == 0
        assert _query_db(tmp_path, "SELECT count(*) FROM t") == [(2,)]


# ---------------------------------------------------------------------------
# SCRIPT blocks and EXECUTE SCRIPT
# ---------------------------------------------------------------------------


class TestScriptBlocks:
    def test_script_and_execute(self, tmp_path):
        result = _run_ast(
            "-- !x! BEGIN SCRIPT make_table\n"
            "CREATE TABLE t (x INT);\n"
            "INSERT INTO t VALUES (42);\n"
            "-- !x! END SCRIPT\n"
            "-- !x! EXECUTE SCRIPT make_table",
            tmp_path,
        )
        assert result.returncode == 0
        assert _query_db(tmp_path, "SELECT x FROM t") == [(42,)]


# ---------------------------------------------------------------------------
# ERROR_HALT OFF/ON
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_error_halt_off_recovers(self, tmp_path):
        result = _run_ast(
            "-- !x! ERROR_HALT OFF\n"
            "SELECT * FROM nonexistent_table_xyz;\n"
            "-- !x! ERROR_HALT ON\n"
            "CREATE TABLE survived (x INT);\n"
            "INSERT INTO survived VALUES (1);",
            tmp_path,
        )
        assert result.returncode == 0
        assert _query_db(tmp_path, "SELECT x FROM survived") == [(1,)]


# ---------------------------------------------------------------------------
# ASSERT
# ---------------------------------------------------------------------------


class TestAssert:
    def test_assert_passes(self, tmp_path):
        result = _run_ast("-- !x! ASSERT TRUE", tmp_path)
        assert result.returncode == 0

    def test_assert_fails(self, tmp_path):
        result = _run_ast("-- !x! ASSERT FALSE", tmp_path)
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# Profiling with --ast
# ---------------------------------------------------------------------------


class TestProfiling:
    def test_profile_flag(self, tmp_path):
        result = _run_ast(
            "CREATE TABLE t (x INT);\nINSERT INTO t VALUES (1);",
            tmp_path,
            extra_args=["--profile"],
        )
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Behavioral equivalence: compare --ast vs legacy on same script
# ---------------------------------------------------------------------------


class TestEquivalence:
    def test_control_flow_equivalence(self, tmp_path):
        """Both engines should produce identical database state."""
        script = (
            "-- !x! SUB counter 0\n"
            "CREATE TABLE t (i INT);\n"
            "-- !x! LOOP WHILE (NOT IS_GTE(!{counter}!, 5))\n"
            "-- !x! SUB_ADD counter 1\n"
            "INSERT INTO t VALUES (!!counter!!);\n"
            "-- !x! END LOOP\n"
            "-- !x! IF (TRUE)\n"
            "INSERT INTO t VALUES (99);\n"
            "-- !x! ELSE\n"
            "INSERT INTO t VALUES (0);\n"
            "-- !x! ENDIF"
        )

        # Run with legacy
        legacy_dir = tmp_path / "legacy"
        legacy_dir.mkdir()
        legacy_result = _run_legacy(script, legacy_dir)
        assert legacy_result.returncode == 0
        legacy_rows = _query_db(legacy_dir, "SELECT i FROM t ORDER BY i")

        # Run with AST
        ast_dir = tmp_path / "ast"
        ast_dir.mkdir()
        ast_result = _run_ast(script, ast_dir)
        assert ast_result.returncode == 0
        ast_rows = _query_db(ast_dir, "SELECT i FROM t ORDER BY i")

        assert legacy_rows == ast_rows
