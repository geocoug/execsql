"""Tests for the public Python API (execsql.run)."""

from __future__ import annotations

import sqlite3

import pytest

from execsql import ExecSqlError, run
from execsql.exceptions import ErrInfo


# ---------------------------------------------------------------------------
# Basic execution
# ---------------------------------------------------------------------------


class TestBasicExecution:
    def test_inline_sql(self, tmp_path):
        db = tmp_path / "test.db"
        result = run(
            sql="CREATE TABLE t (id INTEGER);\nINSERT INTO t VALUES (1);",
            dsn=f"sqlite:///{db}",
            new_db=True,
        )
        assert result.success is True
        assert result.commands_run == 2
        assert result.elapsed > 0
        assert result.errors == []

        # Verify data was written
        conn = sqlite3.connect(str(db))
        rows = conn.execute("SELECT id FROM t").fetchall()
        conn.close()
        assert rows == [(1,)]

    def test_script_file(self, tmp_path):
        script = tmp_path / "test.sql"
        script.write_text("CREATE TABLE t (x INT);\nINSERT INTO t VALUES (42);\n")
        db = tmp_path / "test.db"

        result = run(script=script, dsn=f"sqlite:///{db}", new_db=True)
        assert result.success is True
        assert result.commands_run == 2

    def test_in_memory_sqlite(self):
        result = run(
            sql="CREATE TABLE t (x INT);\nINSERT INTO t VALUES (1);",
            dsn="sqlite:///:memory:",
        )
        assert result.success is True

    def test_metacommands(self):
        result = run(
            sql="-- !x! SUB greeting hello\nCREATE TABLE t (val TEXT);",
            dsn="sqlite:///:memory:",
        )
        assert result.success is True
        assert result.variables.get("greeting") == "hello"


# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------


class TestVariables:
    def test_user_variables_in_result(self):
        result = run(
            sql="-- !x! SUB myvar test_value",
            dsn="sqlite:///:memory:",
        )
        assert result.success is True
        assert result.variables["myvar"] == "test_value"

    def test_variables_dict(self, tmp_path):
        db = tmp_path / "test.db"
        result = run(
            sql="CREATE TABLE t (val TEXT);\nINSERT INTO t VALUES ('!!$MYVAR!!');",
            dsn=f"sqlite:///{db}",
            new_db=True,
            variables={"MYVAR": "injected_value"},
        )
        assert result.success is True

        conn = sqlite3.connect(str(db))
        rows = conn.execute("SELECT val FROM t").fetchall()
        conn.close()
        assert rows == [("injected_value",)]

    def test_variables_auto_prefix_dollar(self):
        result = run(
            sql="-- !x! SUB x placeholder",
            dsn="sqlite:///:memory:",
            variables={"NAME": "value"},
        )
        assert result.variables.get("name") == "value"

    def test_system_variables_in_result(self):
        result = run(sql="SELECT 1;", dsn="sqlite:///:memory:")
        assert "script_start_time" in result.variables
        assert "hostname" in result.variables


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_sql_error_captured(self):
        result = run(
            sql="SELECT * FROM nonexistent_table;",
            dsn="sqlite:///:memory:",
        )
        assert result.success is False
        assert len(result.errors) >= 1

    def test_halt_on_error_true_stops(self, tmp_path):
        db = tmp_path / "test.db"
        result = run(
            sql=("CREATE TABLE t (x INT);\nSELECT * FROM nonexistent;\nINSERT INTO t VALUES (1);\n"),
            dsn=f"sqlite:///{db}",
            new_db=True,
            halt_on_error=True,
        )
        assert result.success is False
        # The INSERT should NOT have run
        conn = sqlite3.connect(str(db))
        try:
            rows = conn.execute("SELECT count(*) FROM t").fetchall()
            assert rows == [(0,)]
        finally:
            conn.close()

    def test_halt_on_error_false_continues(self, tmp_path):
        db = tmp_path / "test.db"
        result = run(
            sql=("CREATE TABLE t (x INT);\nSELECT * FROM nonexistent;\nINSERT INTO t VALUES (1);\n"),
            dsn=f"sqlite:///{db}",
            new_db=True,
            halt_on_error=False,
        )
        # Script continued past the error
        assert result.commands_run >= 2

        conn = sqlite3.connect(str(db))
        rows = conn.execute("SELECT count(*) FROM t").fetchall()
        conn.close()
        assert rows == [(1,)]

    def test_raise_on_error(self):
        result = run(
            sql="SELECT * FROM nonexistent;",
            dsn="sqlite:///:memory:",
        )
        with pytest.raises(ExecSqlError) as exc_info:
            result.raise_on_error()
        assert exc_info.value.result is result

    def test_parse_error(self):
        # Unmatched IF should produce a parse error
        with pytest.raises(ErrInfo):
            run(
                sql="-- !x! IF (TRUE)\nSELECT 1;",
                dsn="sqlite:///:memory:",
            )


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


class TestArgValidation:
    def test_both_script_and_sql_raises(self):
        with pytest.raises(ValueError, match="not both"):
            run(script="x.sql", sql="SELECT 1;", dsn="sqlite:///:memory:")

    def test_neither_script_nor_sql_raises(self):
        with pytest.raises(ValueError, match="must be provided"):
            run(dsn="sqlite:///:memory:")

    def test_both_dsn_and_connection_raises(self):
        with pytest.raises(ValueError, match="not both"):
            run(sql="SELECT 1;", dsn="sqlite:///:memory:", connection=object())

    def test_neither_dsn_nor_connection_raises(self):
        with pytest.raises(ValueError, match="must be provided"):
            run(sql="SELECT 1;")


# ---------------------------------------------------------------------------
# Control flow
# ---------------------------------------------------------------------------


class TestControlFlow:
    def test_if_block(self, tmp_path):
        db = tmp_path / "test.db"
        result = run(
            sql=(
                "CREATE TABLE t (x INT);\n"
                "-- !x! IF (TRUE)\n"
                "INSERT INTO t VALUES (1);\n"
                "-- !x! ENDIF\n"
                "-- !x! IF (FALSE)\n"
                "INSERT INTO t VALUES (2);\n"
                "-- !x! ENDIF\n"
            ),
            dsn=f"sqlite:///{db}",
            new_db=True,
        )
        assert result.success is True

        conn = sqlite3.connect(str(db))
        rows = conn.execute("SELECT x FROM t").fetchall()
        conn.close()
        assert rows == [(1,)]

    def test_loop(self, tmp_path):
        db = tmp_path / "test.db"
        result = run(
            sql=(
                "-- !x! SUB counter 0\n"
                "CREATE TABLE t (i INT);\n"
                "-- !x! LOOP WHILE (NOT IS_GTE(!{counter}!, 3))\n"
                "-- !x! SUB_ADD counter 1\n"
                "INSERT INTO t VALUES (!!counter!!);\n"
                "-- !x! END LOOP\n"
            ),
            dsn=f"sqlite:///{db}",
            new_db=True,
        )
        assert result.success is True

        conn = sqlite3.connect(str(db))
        rows = conn.execute("SELECT i FROM t ORDER BY i").fetchall()
        conn.close()
        assert rows == [(1,), (2,), (3,)]

    def test_assert_pass(self):
        result = run(sql="-- !x! ASSERT TRUE", dsn="sqlite:///:memory:")
        assert result.success is True

    def test_assert_fail(self):
        result = run(sql="-- !x! ASSERT FALSE", dsn="sqlite:///:memory:")
        assert result.success is False


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


class TestIsolation:
    def test_multiple_runs_isolated(self):
        """Two sequential runs should not share state."""
        r1 = run(
            sql="-- !x! SUB myvar first\nCREATE TABLE t (x INT);",
            dsn="sqlite:///:memory:",
        )
        r2 = run(
            sql="-- !x! SUB myvar second\nCREATE TABLE t (x INT);",
            dsn="sqlite:///:memory:",
        )
        assert r1.variables["myvar"] == "first"
        assert r2.variables["myvar"] == "second"

    def test_error_does_not_leak(self):
        """A failed run should not affect subsequent runs."""
        r1 = run(sql="SELECT * FROM nonexistent;", dsn="sqlite:///:memory:")
        assert r1.success is False

        r2 = run(
            sql="CREATE TABLE t (x INT);\nINSERT INTO t VALUES (1);",
            dsn="sqlite:///:memory:",
        )
        assert r2.success is True


# ---------------------------------------------------------------------------
# ScriptResult
# ---------------------------------------------------------------------------


class TestScriptResult:
    def test_frozen(self):
        result = run(sql="SELECT 1;", dsn="sqlite:///:memory:")
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]

    def test_repr(self):
        result = run(sql="SELECT 1;", dsn="sqlite:///:memory:")
        r = repr(result)
        assert "ScriptResult" in r
        assert "success=True" in r
