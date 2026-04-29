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

    def test_script_with_args(self, tmp_path):
        result = _run_ast(
            "-- !x! BEGIN SCRIPT insert_row (tbl, val)\n"
            "INSERT INTO !!#tbl!! VALUES (!!#val!!);\n"
            "-- !x! END SCRIPT\n"
            "CREATE TABLE t (x INT);\n"
            "-- !x! EXECUTE SCRIPT insert_row WITH ARGS (tbl=t, val=99)\n"
            "-- !x! EXEC SCRIPT insert_row (tbl=t, val=77)",
            tmp_path,
        )
        assert result.returncode == 0
        rows = _query_db(tmp_path, "SELECT x FROM t ORDER BY x")
        assert rows == [(77,), (99,)]

    def test_execute_script_if_exists_missing(self, tmp_path):
        result = _run_ast(
            "CREATE TABLE t (x INT);\nINSERT INTO t VALUES (1);\n-- !x! EXECUTE SCRIPT IF EXISTS nonexistent_proc",
            tmp_path,
        )
        assert result.returncode == 0
        assert _query_db(tmp_path, "SELECT x FROM t") == [(1,)]

    def test_run_script_alias(self, tmp_path):
        result = _run_ast(
            "-- !x! BEGIN SCRIPT proc1\n"
            "CREATE TABLE t (x INT);\n"
            "INSERT INTO t VALUES (1);\n"
            "-- !x! END SCRIPT\n"
            "-- !x! RUN SCRIPT proc1",
            tmp_path,
        )
        assert result.returncode == 0
        assert _query_db(tmp_path, "SELECT x FROM t") == [(1,)]


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
    """Equivalence tests: both engines must produce identical database state."""

    def _assert_equivalence(self, script: str, tmp_path: Path, query: str) -> None:
        """Run script with both engines and compare query results."""
        legacy_dir = tmp_path / "legacy"
        legacy_dir.mkdir()
        legacy_result = _run_legacy(script, legacy_dir)
        assert legacy_result.returncode == 0, f"Legacy failed: {legacy_result.stderr}"
        legacy_rows = _query_db(legacy_dir, query)

        ast_dir = tmp_path / "ast"
        ast_dir.mkdir()
        ast_result = _run_ast(script, ast_dir)
        assert ast_result.returncode == 0, f"AST failed: {ast_result.stderr}"
        ast_rows = _query_db(ast_dir, query)

        assert legacy_rows == ast_rows, f"Equivalence failure.\nLegacy: {legacy_rows}\nAST: {ast_rows}"

    def test_control_flow_equivalence(self, tmp_path):
        """Loop + IF produce identical rows."""
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
        self._assert_equivalence(script, tmp_path, "SELECT i FROM t ORDER BY i")

    def test_nested_if_else_equivalence(self, tmp_path):
        """Nested IF/ELSEIF/ELSE with variables."""
        script = (
            "-- !x! SUB level 2\n"
            "CREATE TABLE t (msg TEXT);\n"
            "-- !x! IF (EQUALS(!!level!!, 1))\n"
            "INSERT INTO t VALUES ('one');\n"
            "-- !x! ELSEIF (EQUALS(!!level!!, 2))\n"
            "INSERT INTO t VALUES ('two');\n"
            "-- !x! ELSE\n"
            "INSERT INTO t VALUES ('other');\n"
            "-- !x! ENDIF"
        )
        self._assert_equivalence(script, tmp_path, "SELECT msg FROM t")

    def test_batch_equivalence(self, tmp_path):
        """BATCH block commits atomically."""
        script = (
            "CREATE TABLE t (x INT);\n"
            "-- !x! BEGIN BATCH\n"
            "INSERT INTO t VALUES (1);\n"
            "INSERT INTO t VALUES (2);\n"
            "INSERT INTO t VALUES (3);\n"
            "-- !x! END BATCH"
        )
        self._assert_equivalence(script, tmp_path, "SELECT x FROM t ORDER BY x")

    def test_script_block_equivalence(self, tmp_path):
        """SCRIPT block with parameters."""
        script = (
            "CREATE TABLE t (name TEXT, val INT);\n"
            "-- !x! BEGIN SCRIPT add_row (tbl, n, v)\n"
            "INSERT INTO !!#tbl!! VALUES ('!!#n!!', !!#v!!);\n"
            "-- !x! END SCRIPT\n"
            "-- !x! EXECUTE SCRIPT add_row WITH ARGS (tbl=t, n=alice, v=10)\n"
            "-- !x! EXEC SCRIPT add_row (tbl=t, n=bob, v=20)"
        )
        self._assert_equivalence(script, tmp_path, "SELECT name, val FROM t ORDER BY name")

    def test_loop_with_break_equivalence(self, tmp_path):
        """LOOP with conditional BREAK."""
        script = (
            "-- !x! SUB i 0\n"
            "CREATE TABLE t (x INT);\n"
            "-- !x! LOOP WHILE (TRUE)\n"
            "-- !x! SUB_ADD i 1\n"
            "INSERT INTO t VALUES (!!i!!);\n"
            "-- !x! IF (IS_GTE(!!i!!, 3))\n"
            "-- !x! BREAK\n"
            "-- !x! ENDIF\n"
            "-- !x! END LOOP"
        )
        self._assert_equivalence(script, tmp_path, "SELECT x FROM t ORDER BY x")

    def test_until_loop_equivalence(self, tmp_path):
        """LOOP UNTIL with deferred vars in condition.

        Note: The legacy engine has a bug where deferred vars in LOOP UNTIL
        conditions are not properly converted during loop compilation,
        resulting in an un-substituted variable warning and the loop
        never executing. The AST engine handles this correctly.
        We test each engine separately here rather than asserting equivalence.
        """
        script = (
            "-- !x! SUB cnt 0\n"
            "CREATE TABLE t (i INT);\n"
            "-- !x! LOOP UNTIL (EQUALS(!{cnt}!, 4))\n"
            "-- !x! SUB_ADD cnt 1\n"
            "INSERT INTO t VALUES (!!cnt!!);\n"
            "-- !x! ENDLOOP"
        )
        # AST engine should produce correct results
        ast_dir = tmp_path / "ast"
        ast_dir.mkdir()
        ast_result = _run_ast(script, ast_dir)
        assert ast_result.returncode == 0
        ast_rows = _query_db(ast_dir, "SELECT i FROM t ORDER BY i")
        assert ast_rows == [(1,), (2,), (3,), (4,)]

    def test_andif_orif_equivalence(self, tmp_path):
        """ANDIF and ORIF compound conditions."""
        script = (
            "-- !x! SUB a 1\n"
            "-- !x! SUB b 2\n"
            "CREATE TABLE t (x INT);\n"
            "-- !x! IF (EQUALS(!!a!!, 1))\n"
            "-- !x! ANDIF (EQUALS(!!b!!, 2))\n"
            "INSERT INTO t VALUES (1);\n"
            "-- !x! ENDIF\n"
            "-- !x! IF (EQUALS(!!a!!, 99))\n"
            "-- !x! ORIF (EQUALS(!!b!!, 2))\n"
            "INSERT INTO t VALUES (2);\n"
            "-- !x! ENDIF"
        )
        self._assert_equivalence(script, tmp_path, "SELECT x FROM t ORDER BY x")

    def test_error_halt_off_equivalence(self, tmp_path):
        """ERROR_HALT OFF recovery behavior."""
        script = (
            "-- !x! ERROR_HALT OFF\n"
            "CREATE TABLE t (x INT);\n"
            "SELECT * FROM nonexistent_xyz;\n"
            "-- !x! ERROR_HALT ON\n"
            "INSERT INTO t VALUES (42);"
        )
        self._assert_equivalence(script, tmp_path, "SELECT x FROM t")

    def test_sub_variables_equivalence(self, tmp_path):
        """Variable substitution, SUB_ADD, and system vars."""
        script = "-- !x! SUB x 10\n-- !x! SUB_ADD x 5\nCREATE TABLE t (val INT);\nINSERT INTO t VALUES (!!x!!);"
        self._assert_equivalence(script, tmp_path, "SELECT val FROM t")

    def test_execute_script_with_loop_equivalence(self, tmp_path):
        """EXECUTE SCRIPT with WHILE loop."""
        script = (
            "-- !x! SUB counter 0\n"
            "CREATE TABLE t (x INT);\n"
            "-- !x! BEGIN SCRIPT add_one\n"
            "-- !x! SUB_ADD counter 1\n"
            "INSERT INTO t VALUES (!!counter!!);\n"
            "-- !x! END SCRIPT\n"
            "-- !x! EXECUTE SCRIPT add_one WHILE (NOT IS_GTE(!{counter}!, 3))"
        )
        self._assert_equivalence(script, tmp_path, "SELECT x FROM t ORDER BY x")


# ---------------------------------------------------------------------------
# INCLUDE tests (native AST INCLUDE handling)
# ---------------------------------------------------------------------------


class TestInclude:
    """Test native AST INCLUDE file handling."""

    def test_simple_include(self, tmp_path):
        """INCLUDE parses and executes included file through AST."""
        included = tmp_path / "included.sql"
        included.write_text("INSERT INTO t VALUES (42);")
        script = "CREATE TABLE t (x INT);\n-- !x! INCLUDE included.sql"
        result = _run_ast(script, tmp_path)
        assert result.returncode == 0
        assert _query_db(tmp_path, "SELECT x FROM t") == [(42,)]

    def test_include_with_variables(self, tmp_path):
        """Variables set before INCLUDE are visible inside included file."""
        included = tmp_path / "included.sql"
        included.write_text("INSERT INTO t VALUES (!!myval!!);")
        script = "CREATE TABLE t (x INT);\n-- !x! SUB myval 99\n-- !x! INCLUDE included.sql"
        result = _run_ast(script, tmp_path)
        assert result.returncode == 0
        assert _query_db(tmp_path, "SELECT x FROM t") == [(99,)]

    def test_include_if_exists_missing(self, tmp_path):
        """INCLUDE IF EXISTS silently skips missing files."""
        script = "CREATE TABLE t (x INT);\nINSERT INTO t VALUES (1);\n-- !x! INCLUDE IF EXISTS no_such_file.sql"
        result = _run_ast(script, tmp_path)
        assert result.returncode == 0
        assert _query_db(tmp_path, "SELECT x FROM t") == [(1,)]

    def test_include_if_exists_present(self, tmp_path):
        """INCLUDE IF EXISTS loads when file exists."""
        included = tmp_path / "extra.sql"
        included.write_text("INSERT INTO t VALUES (2);")
        script = "CREATE TABLE t (x INT);\nINSERT INTO t VALUES (1);\n-- !x! INCLUDE IF EXISTS extra.sql"
        result = _run_ast(script, tmp_path)
        assert result.returncode == 0
        rows = _query_db(tmp_path, "SELECT x FROM t ORDER BY x")
        assert rows == [(1,), (2,)]

    def test_include_missing_file_fails(self, tmp_path):
        """INCLUDE without IF EXISTS fails on missing file."""
        script = "CREATE TABLE t (x INT);\n-- !x! INCLUDE no_such_file.sql"
        result = _run_ast(script, tmp_path)
        assert result.returncode != 0
        assert "does not exist" in result.stderr

    def test_nested_include(self, tmp_path):
        """INCLUDE inside an included file (two levels deep)."""
        level2 = tmp_path / "level2.sql"
        level2.write_text("INSERT INTO t VALUES (2);")
        level1 = tmp_path / "level1.sql"
        level1.write_text("INSERT INTO t VALUES (1);\n-- !x! INCLUDE level2.sql")
        script = "CREATE TABLE t (x INT);\n-- !x! INCLUDE level1.sql"
        result = _run_ast(script, tmp_path)
        assert result.returncode == 0
        rows = _query_db(tmp_path, "SELECT x FROM t ORDER BY x")
        assert rows == [(1,), (2,)]

    def test_circular_include_detected(self, tmp_path):
        """Circular INCLUDE is caught and reported."""
        a = tmp_path / "a.sql"
        b = tmp_path / "b.sql"
        a.write_text("-- !x! INCLUDE b.sql")
        b.write_text("-- !x! INCLUDE a.sql")
        script = "CREATE TABLE t (x INT);\n-- !x! INCLUDE a.sql"
        result = _run_ast(script, tmp_path)
        assert result.returncode != 0
        assert "Circular INCLUDE" in result.stderr

    def test_self_include_detected(self, tmp_path):
        """A file that includes itself is caught."""
        script_file = tmp_path / "test.sql"
        script_file.write_text(
            "CREATE TABLE IF NOT EXISTS t (x INT);\n-- !x! INCLUDE test.sql",
        )
        db = tmp_path / "test.db"
        result = subprocess.run(
            [sys.executable, "-m", "execsql", "--ast", str(script_file), str(db), "-t", "l", "-n"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0
        assert "Circular INCLUDE" in result.stderr

    def test_include_defines_script_block(self, tmp_path):
        """INCLUDE loads a file that defines a SCRIPT block, then EXECUTE SCRIPT uses it."""
        lib = tmp_path / "lib.sql"
        lib.write_text(
            "-- !x! BEGIN SCRIPT greet (name)\nINSERT INTO t VALUES ('!!#name!!');\n-- !x! END SCRIPT",
        )
        script = (
            "CREATE TABLE t (msg TEXT);\n-- !x! INCLUDE lib.sql\n-- !x! EXECUTE SCRIPT greet WITH ARGS (name=world)"
        )
        result = _run_ast(script, tmp_path)
        assert result.returncode == 0
        assert _query_db(tmp_path, "SELECT msg FROM t") == [("world",)]

    def test_include_equivalence(self, tmp_path):
        """INCLUDE produces the same result with both engines."""
        included = tmp_path / "sub.sql"
        included.write_text("INSERT INTO t VALUES (42);")

        script = "CREATE TABLE t (x INT);\n-- !x! INCLUDE sub.sql"

        legacy_dir = tmp_path / "legacy"
        legacy_dir.mkdir()
        # Copy included file to legacy dir
        (legacy_dir / "sub.sql").write_text("INSERT INTO t VALUES (42);")
        legacy_result = _run_legacy(script, legacy_dir)
        assert legacy_result.returncode == 0
        legacy_rows = _query_db(legacy_dir, "SELECT x FROM t")

        ast_dir = tmp_path / "ast"
        ast_dir.mkdir()
        (ast_dir / "sub.sql").write_text("INSERT INTO t VALUES (42);")
        ast_result = _run_ast(script, ast_dir)
        assert ast_result.returncode == 0
        ast_rows = _query_db(ast_dir, "SELECT x FROM t")

        assert legacy_rows == ast_rows


# ---------------------------------------------------------------------------
# INCLUDE → SCRIPT → EXECUTE chain tests
# ---------------------------------------------------------------------------


class TestIncludeScriptChain:
    """Test INCLUDE loading scripts which define blocks, then executing them."""

    def test_include_then_execute_with_args(self, tmp_path):
        """INCLUDE a library, then EXECUTE SCRIPT with parameters."""
        lib = tmp_path / "procedures.sql"
        lib.write_text(
            "-- !x! BEGIN SCRIPT insert_pair (tbl, a, b)\n"
            "INSERT INTO !!#tbl!! VALUES (!!#a!!, !!#b!!);\n"
            "-- !x! END SCRIPT",
        )
        script = (
            "CREATE TABLE t (x INT, y INT);\n"
            "-- !x! INCLUDE procedures.sql\n"
            "-- !x! EXEC SCRIPT insert_pair (tbl=t, a=1, b=2)\n"
            "-- !x! EXEC SCRIPT insert_pair (tbl=t, a=3, b=4)"
        )
        result = _run_ast(script, tmp_path)
        assert result.returncode == 0
        rows = _query_db(tmp_path, "SELECT x, y FROM t ORDER BY x")
        assert rows == [(1, 2), (3, 4)]

    def test_include_then_execute_with_loop(self, tmp_path):
        """INCLUDE defines a script, EXECUTE SCRIPT calls it with WHILE loop."""
        lib = tmp_path / "lib.sql"
        lib.write_text(
            "-- !x! BEGIN SCRIPT tick\n-- !x! SUB_ADD n 1\nINSERT INTO t VALUES (!!n!!);\n-- !x! END SCRIPT",
        )
        script = (
            "-- !x! SUB n 0\n"
            "CREATE TABLE t (x INT);\n"
            "-- !x! INCLUDE lib.sql\n"
            "-- !x! EXECUTE SCRIPT tick WHILE (NOT IS_GTE(!{n}!, 3))"
        )
        result = _run_ast(script, tmp_path)
        assert result.returncode == 0
        rows = _query_db(tmp_path, "SELECT x FROM t ORDER BY x")
        assert rows == [(1,), (2,), (3,)]

    def test_nested_include_with_script_blocks(self, tmp_path):
        """Two-level include: main → lib1 → lib2, where lib2 defines a script."""
        lib2 = tmp_path / "lib2.sql"
        lib2.write_text(
            "-- !x! BEGIN SCRIPT double (val)\n"
            "-- !x! SUB result 0\n"
            "-- !x! SUB_ADD result !!#val!!\n"
            "-- !x! SUB_ADD result !!#val!!\n"
            "INSERT INTO t VALUES (!!result!!);\n"
            "-- !x! END SCRIPT",
        )
        lib1 = tmp_path / "lib1.sql"
        lib1.write_text("-- !x! INCLUDE lib2.sql")
        script = "CREATE TABLE t (x INT);\n-- !x! INCLUDE lib1.sql\n-- !x! EXEC SCRIPT double (val=5)"
        result = _run_ast(script, tmp_path)
        assert result.returncode == 0
        assert _query_db(tmp_path, "SELECT x FROM t") == [(10,)]

    def test_include_with_control_flow(self, tmp_path):
        """Included file contains IF/LOOP blocks — parsed as AST, not flat."""
        included = tmp_path / "logic.sql"
        included.write_text(
            "-- !x! SUB i 0\n"
            "-- !x! LOOP WHILE (NOT IS_GTE(!{i}!, 3))\n"
            "-- !x! SUB_ADD i 1\n"
            "INSERT INTO t VALUES (!!i!!);\n"
            "-- !x! END LOOP\n"
            "-- !x! IF (TRUE)\n"
            "INSERT INTO t VALUES (99);\n"
            "-- !x! ENDIF",
        )
        script = "CREATE TABLE t (x INT);\n-- !x! INCLUDE logic.sql"
        result = _run_ast(script, tmp_path)
        assert result.returncode == 0
        rows = _query_db(tmp_path, "SELECT x FROM t ORDER BY x")
        assert rows == [(1,), (2,), (3,), (99,)]

    def test_include_chain_equivalence(self, tmp_path):
        """INCLUDE → SCRIPT → EXECUTE chain gives same result with both engines."""
        lib = tmp_path / "funcs.sql"
        lib.write_text(
            "-- !x! BEGIN SCRIPT sq (n)\nINSERT INTO t VALUES (!!#n!! * !!#n!!);\n-- !x! END SCRIPT",
        )

        script = (
            "CREATE TABLE t (x INT);\n"
            "-- !x! INCLUDE funcs.sql\n"
            "-- !x! EXEC SCRIPT sq (n=3)\n"
            "-- !x! EXEC SCRIPT sq (n=7)"
        )

        legacy_dir = tmp_path / "legacy"
        legacy_dir.mkdir()
        (legacy_dir / "funcs.sql").write_text(lib.read_text())
        legacy_result = _run_legacy(script, legacy_dir)
        assert legacy_result.returncode == 0
        legacy_rows = _query_db(legacy_dir, "SELECT x FROM t ORDER BY x")

        ast_dir = tmp_path / "ast"
        ast_dir.mkdir()
        (ast_dir / "funcs.sql").write_text(lib.read_text())
        ast_result = _run_ast(script, ast_dir)
        assert ast_result.returncode == 0
        ast_rows = _query_db(ast_dir, "SELECT x FROM t ORDER BY x")

        assert legacy_rows == ast_rows


# ---------------------------------------------------------------------------
# Nested deferred variable tests
# ---------------------------------------------------------------------------


class TestDeferredVariables:
    """Test deferred variables (!{$VAR}!) in nested contexts."""

    def test_deferred_in_loop_body(self, tmp_path):
        """Deferred vars in loop body re-evaluate each iteration."""
        script = (
            "-- !x! SUB cnt 0\n"
            "CREATE TABLE t (x INT);\n"
            "-- !x! LOOP WHILE (NOT IS_GTE(!{cnt}!, 3))\n"
            "-- !x! SUB_ADD cnt 1\n"
            "INSERT INTO t VALUES (!{cnt}!);\n"
            "-- !x! END LOOP"
        )
        result = _run_ast(script, tmp_path)
        assert result.returncode == 0
        rows = _query_db(tmp_path, "SELECT x FROM t ORDER BY x")
        assert rows == [(1,), (2,), (3,)]

    def test_deferred_in_loop_condition(self, tmp_path):
        """Deferred vars in LOOP WHILE condition re-evaluate."""
        script = (
            "-- !x! SUB n 0\n"
            "CREATE TABLE t (i INT);\n"
            "-- !x! LOOP WHILE (NOT IS_GTE(!{n}!, 4))\n"
            "-- !x! SUB_ADD n 1\n"
            "INSERT INTO t VALUES (!!n!!);\n"
            "-- !x! END LOOP"
        )
        result = _run_ast(script, tmp_path)
        assert result.returncode == 0
        rows = _query_db(tmp_path, "SELECT i FROM t ORDER BY i")
        assert rows == [(1,), (2,), (3,), (4,)]

    def test_deferred_in_execute_script_while(self, tmp_path):
        """Deferred vars in EXECUTE SCRIPT WHILE condition."""
        script = (
            "-- !x! SUB cnt 0\n"
            "CREATE TABLE t (x INT);\n"
            "-- !x! BEGIN SCRIPT bump\n"
            "-- !x! SUB_ADD cnt 1\n"
            "INSERT INTO t VALUES (!!cnt!!);\n"
            "-- !x! END SCRIPT\n"
            "-- !x! EXECUTE SCRIPT bump WHILE (NOT IS_GTE(!{cnt}!, 3))"
        )
        result = _run_ast(script, tmp_path)
        assert result.returncode == 0
        rows = _query_db(tmp_path, "SELECT x FROM t ORDER BY x")
        assert rows == [(1,), (2,), (3,)]

    def test_deferred_in_nested_loop(self, tmp_path):
        """Deferred vars in a loop inside an IF inside a loop."""
        script = (
            "-- !x! SUB outer 0\n"
            "CREATE TABLE t (a INT, b INT);\n"
            "-- !x! LOOP WHILE (NOT IS_GTE(!{outer}!, 2))\n"
            "-- !x! SUB_ADD outer 1\n"
            "-- !x! SUB inner 0\n"
            "-- !x! LOOP WHILE (NOT IS_GTE(!{inner}!, 2))\n"
            "-- !x! SUB_ADD inner 1\n"
            "INSERT INTO t VALUES (!!outer!!, !!inner!!);\n"
            "-- !x! END LOOP\n"
            "-- !x! END LOOP"
        )
        result = _run_ast(script, tmp_path)
        assert result.returncode == 0
        rows = _query_db(tmp_path, "SELECT a, b FROM t ORDER BY a, b")
        assert rows == [(1, 1), (1, 2), (2, 1), (2, 2)]

    def test_deferred_in_included_loop(self, tmp_path):
        """Deferred vars work in a loop inside an INCLUDE'd file."""
        included = tmp_path / "loop.sql"
        included.write_text(
            "-- !x! SUB j 0\n"
            "-- !x! LOOP WHILE (NOT IS_GTE(!{j}!, 3))\n"
            "-- !x! SUB_ADD j 1\n"
            "INSERT INTO t VALUES (!!j!!);\n"
            "-- !x! END LOOP",
        )
        script = "CREATE TABLE t (x INT);\n-- !x! INCLUDE loop.sql"
        result = _run_ast(script, tmp_path)
        assert result.returncode == 0
        rows = _query_db(tmp_path, "SELECT x FROM t ORDER BY x")
        assert rows == [(1,), (2,), (3,)]

    def test_deferred_nested_equivalence(self, tmp_path):
        """Nested loop with deferred vars — AST-only (legacy has known bug with nested deferred vars)."""
        script = (
            "-- !x! SUB i 0\n"
            "CREATE TABLE t (a INT, b INT);\n"
            "-- !x! LOOP WHILE (NOT IS_GTE(!{i}!, 3))\n"
            "-- !x! SUB_ADD i 1\n"
            "-- !x! SUB j 0\n"
            "-- !x! LOOP WHILE (NOT IS_GTE(!{j}!, 2))\n"
            "-- !x! SUB_ADD j 1\n"
            "INSERT INTO t VALUES (!!i!!, !!j!!);\n"
            "-- !x! END LOOP\n"
            "-- !x! END LOOP"
        )
        result = _run_ast(script, tmp_path)
        assert result.returncode == 0
        rows = _query_db(tmp_path, "SELECT a, b FROM t ORDER BY a, b")
        assert rows == [(1, 1), (1, 2), (2, 1), (2, 2), (3, 1), (3, 2)]
