"""In-process coverage tests for execsql.script.executor.

The existing tests/test_executor.py runs the AST executor via subprocess,
which means coverage.py never sees those lines.  This module exercises
the executor through the in-process ``execsql.run()`` API so that real
coverage data is collected.

Targets:
- LOOP WHILE / UNTIL — body, BREAK, deferred-var conversion
- BEGIN BATCH / END BATCH
- BEGIN SCRIPT / EXECUTE SCRIPT (with args, defaults, missing params)
- INCLUDE / INCLUDE IF EXISTS / circular detection / tilde expansion
- ELSEIF and ELSE branches in IF
- Profiling (ctx.profile_data) and step_mode
- _FakeScriptCmd / _node_cmd_type / _node_cmd_text helpers
- _convert_deferred_vars regex
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from execsql import run
from execsql.script.ast import (
    BatchBlock,
    IfBlock,
    IncludeDirective,
    LoopBlock,
    ScriptBlock,
    SqlBlock,
)
from execsql.script.executor import (
    _BreakLoop,
    _BREAK_RX,
    _convert_deferred_vars,
    _FakeScriptCmd,
    _node_cmd_text,
    _node_cmd_type,
)
from execsql.script.parser import parse_string


# ---------------------------------------------------------------------------
# Pure helper tests — exercised in isolation
# ---------------------------------------------------------------------------


class TestConvertDeferredVars:
    def test_deferred_to_regular(self) -> None:
        assert _convert_deferred_vars("!{$VAR}!") == "!!$VAR!!"

    def test_deferred_with_scope_prefix(self) -> None:
        assert _convert_deferred_vars("!{~local}!") == "!!~local!!"
        assert _convert_deferred_vars("!{#param}!") == "!!#param!!"
        assert _convert_deferred_vars("!{&counter}!") == "!!&counter!!"

    def test_mixed_text_preserves_non_deferred(self) -> None:
        assert _convert_deferred_vars("x = !{$A}! and !!$B!!") == "x = !!$A!! and !!$B!!"

    def test_no_deferred_vars_unchanged(self) -> None:
        assert _convert_deferred_vars("SELECT * FROM t;") == "SELECT * FROM t;"


class TestBreakRegex:
    def test_break_matches(self) -> None:
        assert _BREAK_RX.match("BREAK")
        assert _BREAK_RX.match("break")
        assert _BREAK_RX.match("  BREAK  ")

    def test_break_no_match_other(self) -> None:
        assert not _BREAK_RX.match("BREAKER")
        assert not _BREAK_RX.match("BREAK foo")


class TestBreakLoopException:
    def test_is_exception_class(self) -> None:
        assert issubclass(_BreakLoop, Exception)
        with pytest.raises(_BreakLoop):
            raise _BreakLoop


class TestNodeCmdHelpers:
    def test_node_cmd_type_sql(self) -> None:
        tree = parse_string("SELECT 1;")
        sql_node = tree.body[0].body[0] if isinstance(tree.body[0], SqlBlock) else tree.body[0]
        assert _node_cmd_type(sql_node) == "sql"

    def test_node_cmd_type_meta(self) -> None:
        tree = parse_string("-- !x! SUB x 1\n")
        assert _node_cmd_type(tree.body[0]) == "cmd"

    def test_node_cmd_text_sql(self) -> None:
        tree = parse_string("SELECT 1;")
        sql_node = tree.body[0].body[0] if isinstance(tree.body[0], SqlBlock) else tree.body[0]
        assert "SELECT 1" in _node_cmd_text(sql_node)

    def test_node_cmd_text_meta(self) -> None:
        tree = parse_string("-- !x! SUB x 1\n")
        assert "SUB x 1" in _node_cmd_text(tree.body[0])

    def test_node_cmd_text_if(self) -> None:
        tree = parse_string("-- !x! IF(1=1)\nSELECT 1;\n-- !x! ENDIF\n")
        if_node = next(n for n in tree.body if isinstance(n, IfBlock))
        assert "IF" in _node_cmd_text(if_node)

    def test_node_cmd_text_loop(self) -> None:
        tree = parse_string("-- !x! LOOP WHILE(0)\nSELECT 1;\n-- !x! END LOOP\n")
        loop_node = next(n for n in tree.body if isinstance(n, LoopBlock))
        assert "LOOP" in _node_cmd_text(loop_node)

    def test_node_cmd_text_batch(self) -> None:
        tree = parse_string("-- !x! BEGIN BATCH\nSELECT 1;\n-- !x! END BATCH\n")
        batch_node = next(n for n in tree.body if isinstance(n, BatchBlock))
        assert "BATCH" in _node_cmd_text(batch_node)

    def test_node_cmd_text_script_block(self) -> None:
        tree = parse_string("-- !x! BEGIN SCRIPT foo\nSELECT 1;\n-- !x! END SCRIPT\n")
        script_node = next(n for n in tree.body if isinstance(n, ScriptBlock))
        assert "SCRIPT" in _node_cmd_text(script_node)

    def test_node_cmd_text_include(self) -> None:
        tree = parse_string("-- !x! INCLUDE foo.sql\n")
        inc_node = next(n for n in tree.body if isinstance(n, IncludeDirective))
        assert "INCLUDE" in _node_cmd_text(inc_node)

    def test_node_cmd_text_execute_script(self) -> None:
        tree = parse_string("-- !x! EXECUTE SCRIPT foo\n")
        ex_node = next(n for n in tree.body if isinstance(n, IncludeDirective))
        assert "EXECUTE SCRIPT" in _node_cmd_text(ex_node)


class TestFakeScriptCmd:
    def test_fake_for_sql(self) -> None:
        tree = parse_string("SELECT 1;", source_name="s.sql")
        node = tree.body[0].body[0] if isinstance(tree.body[0], SqlBlock) else tree.body[0]
        fake = _FakeScriptCmd(node)
        assert fake.command_type == "sql"
        assert fake.source == "s.sql"
        loc, line = fake.current_script_line()
        assert loc == "s.sql"
        assert fake.commandline()

    def test_fake_for_meta(self) -> None:
        tree = parse_string("-- !x! SUB x 1\n", source_name="src.sql")
        fake = _FakeScriptCmd(tree.body[0])
        assert fake.command_type == "cmd"
        assert "SUB x 1" in fake.commandline()


# ---------------------------------------------------------------------------
# In-process executor coverage via api.run()
# ---------------------------------------------------------------------------


class TestLoopExecution:
    def test_loop_while_basic(self, tmp_path: Path) -> None:
        db = tmp_path / "t.db"
        result = run(
            sql=(
                "CREATE TABLE t (i INT);\n"
                "-- !x! sub i 0\n"
                "-- !x! loop while (not is_gte(!{i}!, 3))\n"
                "INSERT INTO t VALUES (!!i!!);\n"
                "-- !x! sub_add i 1\n"
                "-- !x! end loop\n"
            ),
            dsn=f"sqlite:///{db}",
            new_db=True,
        )
        assert result.success, result.errors
        rows = sqlite3.connect(str(db)).execute("SELECT i FROM t ORDER BY i").fetchall()
        assert rows == [(0,), (1,), (2,)]

    def test_loop_until_basic(self, tmp_path: Path) -> None:
        db = tmp_path / "t.db"
        result = run(
            sql=(
                "CREATE TABLE t (i INT);\n"
                "-- !x! sub i 0\n"
                "-- !x! loop until (is_gte(!{i}!, 2))\n"
                "INSERT INTO t VALUES (!!i!!);\n"
                "-- !x! sub_add i 1\n"
                "-- !x! end loop\n"
            ),
            dsn=f"sqlite:///{db}",
            new_db=True,
        )
        assert result.success, result.errors
        rows = sqlite3.connect(str(db)).execute("SELECT i FROM t ORDER BY i").fetchall()
        assert rows == [(0,), (1,)]

    def test_break_exits_loop(self, tmp_path: Path) -> None:
        db = tmp_path / "t.db"
        result = run(
            sql=(
                "CREATE TABLE t (i INT);\n"
                "-- !x! sub i 0\n"
                "-- !x! loop while (not is_gte(!{i}!, 10))\n"
                "INSERT INTO t VALUES (!!i!!);\n"
                "-- !x! sub_add i 1\n"
                "-- !x! if (equals(!!i!!, 2))\n"
                "-- !x! break\n"
                "-- !x! endif\n"
                "-- !x! end loop\n"
            ),
            dsn=f"sqlite:///{db}",
            new_db=True,
        )
        assert result.success, result.errors
        rows = sqlite3.connect(str(db)).execute("SELECT count(*) FROM t").fetchall()
        assert rows[0][0] == 2

    def test_break_outside_loop_raises(self) -> None:
        result = run(sql="-- !x! break\n", dsn="sqlite:///:memory:")
        assert result.success is False


class TestBatchBlock:
    def test_batch_body_executes(self, tmp_path: Path) -> None:
        db = tmp_path / "t.db"
        result = run(
            sql=(
                "CREATE TABLE t (id INT);\n"
                "-- !x! BEGIN BATCH\n"
                "INSERT INTO t VALUES (1);\n"
                "INSERT INTO t VALUES (2);\n"
                "-- !x! END BATCH\n"
            ),
            dsn=f"sqlite:///{db}",
            new_db=True,
        )
        assert result.success
        rows = sqlite3.connect(str(db)).execute("SELECT count(*) FROM t").fetchall()
        assert rows[0][0] == 2


class TestScriptBlocks:
    def test_execute_script_no_args(self, tmp_path: Path) -> None:
        db = tmp_path / "t.db"
        result = run(
            sql=(
                "-- !x! BEGIN SCRIPT init\n"
                "CREATE TABLE t (x INT);\n"
                "INSERT INTO t VALUES (1);\n"
                "-- !x! END SCRIPT\n"
                "-- !x! EXECUTE SCRIPT init\n"
            ),
            dsn=f"sqlite:///{db}",
            new_db=True,
        )
        assert result.success
        rows = sqlite3.connect(str(db)).execute("SELECT count(*) FROM t").fetchall()
        assert rows[0][0] == 1

    def test_execute_script_with_args(self, tmp_path: Path) -> None:
        db = tmp_path / "t.db"
        result = run(
            sql=(
                "-- !x! BEGIN SCRIPT setup (name)\n"
                "CREATE TABLE !!#name!! (id INT);\n"
                "-- !x! END SCRIPT\n"
                "-- !x! EXECUTE SCRIPT setup WITH ARGS (name=mytbl)\n"
            ),
            dsn=f"sqlite:///{db}",
            new_db=True,
        )
        assert result.success
        rows = (
            sqlite3.connect(str(db))
            .execute(
                "SELECT name FROM sqlite_master WHERE type='table'",
            )
            .fetchall()
        )
        assert ("mytbl",) in rows

    def test_execute_script_missing_required_param(self) -> None:
        result = run(
            sql=(
                "-- !x! BEGIN SCRIPT must_have (required_name)\n"
                "CREATE TABLE !!#required_name!! (id INT);\n"
                "-- !x! END SCRIPT\n"
                "-- !x! EXECUTE SCRIPT must_have\n"
            ),
            dsn="sqlite:///:memory:",
        )
        assert result.success is False

    def test_execute_script_unknown_target_errors(self) -> None:
        result = run(
            sql="-- !x! EXECUTE SCRIPT nonexistent\n",
            dsn="sqlite:///:memory:",
        )
        assert result.success is False

    def test_execute_script_if_exists_missing_ok(self) -> None:
        result = run(
            sql="-- !x! EXECUTE SCRIPT IF EXISTS nope\n",
            dsn="sqlite:///:memory:",
        )
        assert result.success is True

    def test_execute_script_in_loop_while(self, tmp_path: Path) -> None:
        db = tmp_path / "t.db"
        result = run(
            sql=(
                "CREATE TABLE t (i INT);\n"
                "-- !x! sub i 0\n"
                "-- !x! begin script body\n"
                "INSERT INTO t VALUES (!!i!!);\n"
                "-- !x! sub_add i 1\n"
                "-- !x! end script\n"
                "-- !x! execute script body while (not is_gte(!{i}!, 3))\n"
            ),
            dsn=f"sqlite:///{db}",
            new_db=True,
        )
        assert result.success, result.errors
        rows = sqlite3.connect(str(db)).execute("SELECT count(*) FROM t").fetchall()
        assert rows[0][0] == 3


class TestIncludeDirective:
    def test_include_executes(self, tmp_path: Path) -> None:
        inc = tmp_path / "inc.sql"
        inc.write_text("CREATE TABLE inc_t (x INT);\nINSERT INTO inc_t VALUES (42);\n")
        db = tmp_path / "t.db"
        result = run(
            sql=f"-- !x! INCLUDE {inc}\n",
            dsn=f"sqlite:///{db}",
            new_db=True,
        )
        assert result.success
        rows = sqlite3.connect(str(db)).execute("SELECT x FROM inc_t").fetchall()
        assert rows == [(42,)]

    def test_include_missing_raises(self, tmp_path: Path) -> None:
        result = run(
            sql=f"-- !x! INCLUDE {tmp_path}/nope.sql\n",
            dsn="sqlite:///:memory:",
        )
        assert result.success is False

    def test_include_if_exists_missing_ok(self, tmp_path: Path) -> None:
        result = run(
            sql=f"-- !x! INCLUDE IF EXISTS {tmp_path}/nope.sql\n",
            dsn="sqlite:///:memory:",
        )
        assert result.success is True

    def test_include_quoted_target(self, tmp_path: Path) -> None:
        inc = tmp_path / "with space.sql"
        inc.write_text("CREATE TABLE q_t (x INT);")
        db = tmp_path / "t.db"
        result = run(
            sql=f'-- !x! INCLUDE "{inc}"\n',
            dsn=f"sqlite:///{db}",
            new_db=True,
        )
        assert result.success
        rows = (
            sqlite3.connect(str(db))
            .execute(
                "SELECT name FROM sqlite_master WHERE name='q_t'",
            )
            .fetchall()
        )
        assert rows == [("q_t",)]

    def test_circular_include_raises(self, tmp_path: Path) -> None:
        a = tmp_path / "a.sql"
        b = tmp_path / "b.sql"
        a.write_text(f"-- !x! INCLUDE {b}\n")
        b.write_text(f"-- !x! INCLUDE {a}\n")
        result = run(
            sql=f"-- !x! INCLUDE {a}\n",
            dsn="sqlite:///:memory:",
        )
        assert result.success is False


class TestIfElseifElse:
    def test_elseif_branch(self, tmp_path: Path) -> None:
        db = tmp_path / "t.db"
        result = run(
            sql=(
                "CREATE TABLE t (which TEXT);\n"
                "-- !x! sub n 2\n"
                "-- !x! if (equals(!!n!!, 1))\n"
                "INSERT INTO t VALUES ('one');\n"
                "-- !x! elseif (equals(!!n!!, 2))\n"
                "INSERT INTO t VALUES ('two');\n"
                "-- !x! else\n"
                "INSERT INTO t VALUES ('other');\n"
                "-- !x! endif\n"
            ),
            dsn=f"sqlite:///{db}",
            new_db=True,
        )
        assert result.success, result.errors
        rows = sqlite3.connect(str(db)).execute("SELECT which FROM t").fetchall()
        assert rows == [("two",)]

    def test_else_branch(self, tmp_path: Path) -> None:
        db = tmp_path / "t.db"
        result = run(
            sql=(
                "CREATE TABLE t (which TEXT);\n"
                "-- !x! sub n 99\n"
                "-- !x! if (equals(!!n!!, 1))\n"
                "INSERT INTO t VALUES ('one');\n"
                "-- !x! else\n"
                "INSERT INTO t VALUES ('other');\n"
                "-- !x! endif\n"
            ),
            dsn=f"sqlite:///{db}",
            new_db=True,
        )
        assert result.success, result.errors
        rows = sqlite3.connect(str(db)).execute("SELECT which FROM t").fetchall()
        assert rows == [("other",)]

    def test_if_with_andif_short_circuit(self, tmp_path: Path) -> None:
        db = tmp_path / "t.db"
        result = run(
            sql=(
                "CREATE TABLE t (x INT);\n"
                "-- !x! sub flag yes\n"
                "-- !x! if (sub_defined(flag))\n"
                "-- !x! andif (equals(!!flag!!, yes))\n"
                "INSERT INTO t VALUES (1);\n"
                "-- !x! endif\n"
            ),
            dsn=f"sqlite:///{db}",
            new_db=True,
        )
        assert result.success, result.errors
        rows = sqlite3.connect(str(db)).execute("SELECT x FROM t").fetchall()
        assert rows == [(1,)]


class TestExecuteScriptInBatch:
    """EXECUTE SCRIPT inside a BEGIN BATCH (BatchBlock + ScriptBlock interaction)."""

    def test_script_in_batch(self, tmp_path: Path) -> None:
        db = tmp_path / "t.db"
        result = run(
            sql=(
                "-- !x! begin script body\n"
                "CREATE TABLE t (x INT);\n"
                "-- !x! end script\n"
                "-- !x! begin batch\n"
                "-- !x! execute script body\n"
                "-- !x! end batch\n"
                "INSERT INTO t VALUES (1);\n"
            ),
            dsn=f"sqlite:///{db}",
            new_db=True,
        )
        assert result.success, result.errors
