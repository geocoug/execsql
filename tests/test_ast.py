"""Tests for AST node definitions in execsql.script.ast."""

from __future__ import annotations

import pytest

from execsql.script.ast import (
    BatchBlock,
    Comment,
    ConditionModifier,
    ElseIfClause,
    IfBlock,
    IncludeDirective,
    LoopBlock,
    MetaCommandStatement,
    Node,
    Script,
    ScriptBlock,
    SourceSpan,
    SqlBlock,
    SqlStatement,
    format_tree,
)


# ---------------------------------------------------------------------------
# SourceSpan
# ---------------------------------------------------------------------------


class TestSourceSpan:
    def test_single_line(self):
        span = SourceSpan(file="test.sql", start_line=10)
        assert span.file == "test.sql"
        assert span.start_line == 10
        assert span.end_line is None
        assert span.effective_end_line == 10

    def test_multi_line(self):
        span = SourceSpan(file="test.sql", start_line=5, end_line=15)
        assert span.effective_end_line == 15

    def test_str_single_line(self):
        span = SourceSpan(file="pipeline.sql", start_line=42)
        assert str(span) == "pipeline.sql:42"

    def test_str_multi_line(self):
        span = SourceSpan(file="pipeline.sql", start_line=10, end_line=20)
        assert str(span) == "pipeline.sql:10-20"

    def test_str_same_start_end(self):
        span = SourceSpan(file="test.sql", start_line=5, end_line=5)
        assert str(span) == "test.sql:5"

    def test_frozen(self):
        span = SourceSpan(file="test.sql", start_line=1)
        with pytest.raises(AttributeError):
            span.file = "other.sql"  # type: ignore[misc]

    def test_equality(self):
        a = SourceSpan(file="a.sql", start_line=1, end_line=5)
        b = SourceSpan(file="a.sql", start_line=1, end_line=5)
        assert a == b

    def test_hashable(self):
        span = SourceSpan(file="a.sql", start_line=1)
        assert hash(span) == hash(SourceSpan(file="a.sql", start_line=1))


# ---------------------------------------------------------------------------
# Leaf nodes
# ---------------------------------------------------------------------------


def _span(start: int = 1, end: int | None = None) -> SourceSpan:
    """Helper to create a SourceSpan for test nodes."""
    return SourceSpan(file="test.sql", start_line=start, end_line=end)


class TestSqlStatement:
    def test_basic(self):
        node = SqlStatement(span=_span(1), text="SELECT 1;")
        assert node.text == "SELECT 1;"
        assert node.span.start_line == 1
        assert list(node.children()) == []

    def test_repr(self):
        node = SqlStatement(span=_span(5), text="SELECT * FROM users;")
        r = repr(node)
        assert "SqlStatement" in r
        assert "test.sql:5" in r
        assert "SELECT * FROM users;" in r

    def test_repr_truncates_long_text(self):
        long_sql = "SELECT " + ", ".join(f"col{i}" for i in range(100)) + " FROM t;"
        node = SqlStatement(span=_span(1), text=long_sql)
        r = repr(node)
        assert "..." in r

    def test_walk_yields_self(self):
        node = SqlStatement(span=_span(1), text="SELECT 1;")
        walked = list(node.walk())
        assert walked == [node]


class TestMetaCommandStatement:
    def test_basic(self):
        node = MetaCommandStatement(span=_span(3), command="SUB myvar = hello")
        assert node.command == "SUB myvar = hello"
        assert list(node.children()) == []

    def test_repr(self):
        node = MetaCommandStatement(span=_span(3), command="SUB myvar = hello")
        r = repr(node)
        assert "MetaCommandStatement" in r
        assert "SUB myvar = hello" in r


class TestComment:
    def test_basic(self):
        node = Comment(span=_span(1), text="-- This is a comment")
        assert node.text == "-- This is a comment"
        assert list(node.children()) == []

    def test_repr(self):
        node = Comment(span=_span(1), text="-- comment")
        assert "Comment" in repr(node)


# ---------------------------------------------------------------------------
# Block nodes
# ---------------------------------------------------------------------------


class TestIfBlock:
    def test_simple_if(self):
        body_node = SqlStatement(span=_span(2), text="SELECT 1;")
        node = IfBlock(span=_span(1, 3), condition="HAS_ROWS", body=[body_node])
        children = list(node.children())
        assert children == [body_node]

    def test_if_else(self):
        then_node = SqlStatement(span=_span(2), text="SELECT 1;")
        else_node = SqlStatement(span=_span(4), text="SELECT 2;")
        node = IfBlock(
            span=_span(1, 5),
            condition="HAS_ROWS",
            body=[then_node],
            else_body=[else_node],
        )
        children = list(node.children())
        assert children == [then_node, else_node]

    def test_if_elseif_else(self):
        then_node = SqlStatement(span=_span(2), text="SELECT 1;")
        elseif_node = SqlStatement(span=_span(5), text="SELECT 2;")
        else_node = SqlStatement(span=_span(8), text="SELECT 3;")
        elseif = ElseIfClause(
            condition="ROW_COUNT_GT(5)",
            span=_span(4),
            body=[elseif_node],
        )
        node = IfBlock(
            span=_span(1, 10),
            condition="HAS_ROWS",
            body=[then_node],
            elseif_clauses=[elseif],
            else_body=[else_node],
        )
        children = list(node.children())
        assert children == [then_node, elseif_node, else_node]

    def test_walk_traverses_all(self):
        inner = SqlStatement(span=_span(2), text="SELECT 1;")
        node = IfBlock(span=_span(1, 3), condition="HAS_ROWS", body=[inner])
        walked = list(node.walk())
        assert len(walked) == 2
        assert walked[0] is node
        assert walked[1] is inner

    def test_repr(self):
        node = IfBlock(span=_span(1, 5), condition="HAS_ROWS", body=[], else_body=[])
        r = repr(node)
        assert "IfBlock" in r
        assert "HAS_ROWS" in r

    def test_nested_if(self):
        inner_sql = SqlStatement(span=_span(3), text="SELECT 1;")
        inner_if = IfBlock(span=_span(2, 4), condition="FILE_EXISTS('x')", body=[inner_sql])
        outer = IfBlock(span=_span(1, 5), condition="HAS_ROWS", body=[inner_if])
        walked = list(outer.walk())
        assert len(walked) == 3
        assert walked[0] is outer
        assert walked[1] is inner_if
        assert walked[2] is inner_sql


class TestLoopBlock:
    def test_while_loop(self):
        body_node = SqlStatement(span=_span(2), text="INSERT INTO t VALUES (1);")
        node = LoopBlock(
            span=_span(1, 3),
            loop_type="WHILE",
            condition="HAS_ROWS",
            body=[body_node],
        )
        assert node.loop_type == "WHILE"
        assert list(node.children()) == [body_node]

    def test_until_loop(self):
        node = LoopBlock(
            span=_span(1, 3),
            loop_type="UNTIL",
            condition="ROW_COUNT_EQ(0)",
            body=[],
        )
        assert node.loop_type == "UNTIL"

    def test_repr(self):
        node = LoopBlock(span=_span(1, 5), loop_type="WHILE", condition="HAS_ROWS", body=[])
        r = repr(node)
        assert "WHILE" in r
        assert "HAS_ROWS" in r


class TestBatchBlock:
    def test_basic(self):
        sql = SqlStatement(span=_span(2), text="INSERT INTO t VALUES (1);")
        node = BatchBlock(span=_span(1, 3), body=[sql])
        assert list(node.children()) == [sql]

    def test_repr(self):
        node = BatchBlock(span=_span(1, 3), body=[])
        assert "BatchBlock" in repr(node)


class TestScriptBlock:
    def test_basic(self):
        sql = SqlStatement(span=_span(2), text="SELECT 1;")
        node = ScriptBlock(span=_span(1, 3), name="my_proc", body=[sql])
        assert node.name == "my_proc"
        assert list(node.children()) == [sql]

    def test_with_params(self):
        node = ScriptBlock(
            span=_span(1, 5),
            name="load_data",
            param_names=["table_name", "file_path"],
            body=[],
        )
        assert node.param_names == ["table_name", "file_path"]

    def test_repr(self):
        node = ScriptBlock(span=_span(1, 3), name="my_proc", body=[])
        r = repr(node)
        assert "my_proc" in r
        assert "ScriptBlock" in r

    def test_repr_with_params(self):
        node = ScriptBlock(span=_span(1, 3), name="x", param_names=["a", "b"], body=[])
        assert "params=" in repr(node)


class TestSqlBlock:
    def test_basic(self):
        sql = SqlStatement(span=_span(2, 4), text="SELECT\n  1\nFROM t;")
        node = SqlBlock(span=_span(1, 5), body=[sql])
        assert list(node.children()) == [sql]

    def test_repr(self):
        node = SqlBlock(span=_span(1, 5), body=[])
        assert "SqlBlock" in repr(node)


class TestIncludeDirective:
    def test_include_file(self):
        node = IncludeDirective(span=_span(10), target="helpers.sql")
        assert node.target == "helpers.sql"
        assert node.is_execute_script is False
        assert list(node.children()) == []

    def test_execute_script(self):
        node = IncludeDirective(
            span=_span(20),
            target="load_data",
            is_execute_script=True,
            arguments="table=users, file='data.csv'",
        )
        assert node.is_execute_script is True
        assert node.arguments == "table=users, file='data.csv'"

    def test_looped_execute(self):
        node = IncludeDirective(
            span=_span(30),
            target="process",
            is_execute_script=True,
            loop_type="WHILE",
            loop_condition="HAS_ROWS",
        )
        assert node.loop_type == "WHILE"
        assert node.loop_condition == "HAS_ROWS"

    def test_repr_include(self):
        node = IncludeDirective(span=_span(1), target="helpers.sql")
        r = repr(node)
        assert "INCLUDE" in r
        assert "helpers.sql" in r

    def test_repr_execute_script(self):
        node = IncludeDirective(span=_span(1), target="proc", is_execute_script=True)
        r = repr(node)
        assert "EXECUTE SCRIPT" in r


# ---------------------------------------------------------------------------
# Script (top-level container)
# ---------------------------------------------------------------------------


class TestScript:
    def test_empty_script(self):
        script = Script(source="empty.sql", body=[])
        assert script.source == "empty.sql"
        assert script.span is None
        assert list(script.walk()) == []

    def test_single_statement(self):
        sql = SqlStatement(span=_span(1), text="SELECT 1;")
        script = Script(source="test.sql", body=[sql])
        assert len(script.body) == 1
        assert list(script.walk()) == [sql]

    def test_span_covers_all_nodes(self):
        first = SqlStatement(span=SourceSpan("t.sql", 1), text="SELECT 1;")
        last = SqlStatement(span=SourceSpan("t.sql", 50, 55), text="SELECT 2;")
        script = Script(source="t.sql", body=[first, last])
        span = script.span
        assert span is not None
        assert span.start_line == 1
        assert span.effective_end_line == 55

    def test_walk_traverses_nested(self):
        sql1 = SqlStatement(span=_span(2), text="SELECT 1;")
        sql2 = SqlStatement(span=_span(4), text="SELECT 2;")
        if_block = IfBlock(span=_span(1, 5), condition="HAS_ROWS", body=[sql1], else_body=[sql2])
        sql3 = SqlStatement(span=_span(6), text="SELECT 3;")
        script = Script(source="test.sql", body=[if_block, sql3])
        walked = list(script.walk())
        assert len(walked) == 4
        assert walked[0] is if_block
        assert walked[1] is sql1
        assert walked[2] is sql2
        assert walked[3] is sql3

    def test_repr(self):
        script = Script(source="test.sql", body=[])
        assert "Script" in repr(script)
        assert "test.sql" in repr(script)
        assert "nodes=0" in repr(script)


# ---------------------------------------------------------------------------
# Node base class
# ---------------------------------------------------------------------------


class TestNodeBase:
    def test_children_default_empty(self):
        node = SqlStatement(span=_span(1), text="SELECT 1;")
        assert list(node.children()) == []

    def test_isinstance_check(self):
        sql = SqlStatement(span=_span(1), text="SELECT 1;")
        meta = MetaCommandStatement(span=_span(2), command="SUB x = 1")
        assert isinstance(sql, Node)
        assert isinstance(meta, Node)

    def test_walk_complex_tree(self):
        """Walk a realistic script structure with mixed nesting."""
        comment = Comment(span=_span(1), text="-- Setup")
        sub = MetaCommandStatement(span=_span(2), command="SUB table = users")
        create_sql = SqlStatement(span=_span(3), text="CREATE TABLE t (id INT);")
        insert_sql = SqlStatement(span=_span(5), text="INSERT INTO t VALUES (1);")
        loop = LoopBlock(
            span=_span(4, 6),
            loop_type="WHILE",
            condition="HAS_ROWS",
            body=[insert_sql],
        )
        select_sql = SqlStatement(span=_span(8), text="SELECT 1;")
        if_block = IfBlock(
            span=_span(7, 12),
            condition="ROW_COUNT_GT(0)",
            body=[select_sql],
            else_body=[
                MetaCommandStatement(span=_span(10), command='LOG "No rows"'),
            ],
        )
        script = Script(
            source="complex.sql",
            body=[comment, sub, create_sql, loop, if_block],
        )
        walked = list(script.walk())
        assert len(walked) == 8
        # Verify order: comment, sub, create_sql, loop, insert_sql, if_block, select_sql, log
        assert isinstance(walked[0], Comment)
        assert isinstance(walked[1], MetaCommandStatement)
        assert isinstance(walked[2], SqlStatement)
        assert isinstance(walked[3], LoopBlock)
        assert isinstance(walked[4], SqlStatement)  # insert (child of loop)
        assert isinstance(walked[5], IfBlock)
        assert isinstance(walked[6], SqlStatement)  # select (child of if)
        assert isinstance(walked[7], MetaCommandStatement)  # log (else body)


# ---------------------------------------------------------------------------
# format_tree
# ---------------------------------------------------------------------------


class TestFormatTree:
    def test_empty_script(self):
        script = Script(source="empty.sql", body=[])
        result = format_tree(script)
        assert "empty.sql" in result
        assert "0 nodes" in result

    def test_single_sql(self):
        sql = SqlStatement(span=_span(1), text="SELECT 1;")
        script = Script(source="test.sql", body=[sql])
        result = format_tree(script)
        assert "SQL: SELECT 1;" in result
        assert "[1]" in result

    def test_metacommand(self):
        meta = MetaCommandStatement(span=_span(3), command="SUB x = hello")
        script = Script(source="test.sql", body=[meta])
        result = format_tree(script)
        assert "SUB x = hello" in result

    def test_if_else_tree(self):
        then = SqlStatement(span=_span(2), text="SELECT 1;")
        else_ = SqlStatement(span=_span(4), text="SELECT 2;")
        if_block = IfBlock(
            span=_span(1, 5),
            condition="HAS_ROWS",
            body=[then],
            else_body=[else_],
            else_span=_span(3),
        )
        script = Script(source="test.sql", body=[if_block])
        result = format_tree(script)
        assert "IF (HAS_ROWS)" in result
        assert "[3] ELSE" in result
        assert "SELECT 1;" in result
        assert "SELECT 2;" in result

    def test_if_elseif_tree(self):
        clause = ElseIfClause(
            condition="OTHER",
            span=_span(3),
            body=[SqlStatement(span=_span(4), text="SELECT 2;")],
        )
        if_block = IfBlock(
            span=_span(1, 6),
            condition="COND_A",
            body=[SqlStatement(span=_span(2), text="SELECT 1;")],
            elseif_clauses=[clause],
        )
        script = Script(source="test.sql", body=[if_block])
        result = format_tree(script)
        assert "IF (COND_A)" in result
        assert "ELSEIF (OTHER)" in result

    def test_loop_tree(self):
        body = SqlStatement(span=_span(2), text="DELETE FROM t;")
        loop = LoopBlock(
            span=_span(1, 3),
            loop_type="WHILE",
            condition="HAS_ROWS",
            body=[body],
        )
        script = Script(source="test.sql", body=[loop])
        result = format_tree(script)
        assert "LOOP WHILE (HAS_ROWS)" in result
        assert "DELETE FROM t;" in result

    def test_batch_tree(self):
        sql = SqlStatement(span=_span(2), text="INSERT INTO t VALUES (1);")
        batch = BatchBlock(span=_span(1, 3), body=[sql])
        script = Script(source="test.sql", body=[batch])
        result = format_tree(script)
        assert "BEGIN BATCH" in result

    def test_script_block_tree(self):
        sql = SqlStatement(span=_span(2), text="SELECT 1;")
        sb = ScriptBlock(span=_span(1, 3), name="my_proc", param_names=["x", "y"], body=[sql])
        script = Script(source="test.sql", body=[sb])
        result = format_tree(script)
        assert "SCRIPT my_proc (x, y)" in result

    def test_include_tree(self):
        inc = IncludeDirective(span=_span(1), target="helpers.sql")
        script = Script(source="test.sql", body=[inc])
        result = format_tree(script)
        assert "INCLUDE helpers.sql" in result

    def test_execute_script_tree(self):
        exe = IncludeDirective(
            span=_span(1),
            target="proc",
            is_execute_script=True,
            loop_type="WHILE",
            loop_condition="HAS_ROWS",
        )
        script = Script(source="test.sql", body=[exe])
        result = format_tree(script)
        assert "EXECUTE SCRIPT proc WHILE (HAS_ROWS)" in result

    def test_if_with_condition_modifiers(self):
        if_block = IfBlock(
            span=_span(1, 5),
            condition="equals(!!role!!, admin)",
            condition_modifiers=[
                ConditionModifier(kind="AND", condition="equals(!!active!!, 1)", span=_span(2)),
                ConditionModifier(kind="OR", condition="equals(!!role!!, super)", span=_span(3)),
            ],
            body=[SqlStatement(span=_span(4), text="SELECT 1;")],
        )
        script = Script(source="test.sql", body=[if_block])
        result = format_tree(script)
        assert "IF (equals(!!role!!, admin)) ANDIF (equals(!!active!!, 1)) ORIF (equals(!!role!!, super))" in result

    def test_tree_connectors(self):
        sql1 = SqlStatement(span=_span(1), text="SELECT 1;")
        sql2 = SqlStatement(span=_span(2), text="SELECT 2;")
        script = Script(source="test.sql", body=[sql1, sql2])
        result = format_tree(script)
        lines = result.split("\n")
        # First node uses ├──, last uses └──
        assert "├──" in lines[1]
        assert "└──" in lines[2]

    def test_nested_tree_indentation(self):
        inner = SqlStatement(span=_span(2), text="SELECT 1;")
        loop = LoopBlock(span=_span(1, 3), loop_type="WHILE", condition="C", body=[inner])
        sql = SqlStatement(span=_span(4), text="SELECT 2;")
        script = Script(source="test.sql", body=[loop, sql])
        result = format_tree(script)
        # The inner SELECT should be indented under the loop
        lines = result.split("\n")
        assert any("│" in line and "SELECT 1" in line for line in lines)
