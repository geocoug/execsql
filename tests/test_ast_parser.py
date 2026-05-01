"""Tests for the AST-producing parser in execsql.script.parser."""

from __future__ import annotations

import pytest

from execsql.exceptions import ErrInfo
from execsql.script.ast import (
    BatchBlock,
    Comment,
    IfBlock,
    IncludeDirective,
    LoopBlock,
    MetaCommandStatement,
    Node,
    ScriptBlock,
    SqlBlock,
    SqlStatement,
)
from execsql.script.parser import parse_string


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _body(script_text: str) -> list[Node]:
    """Parse a script string and return its body nodes."""
    return parse_string(script_text).body


def _first(script_text: str) -> Node:
    """Parse and return the first node."""
    nodes = _body(script_text)
    assert len(nodes) >= 1, f"Expected at least 1 node, got {len(nodes)}"
    return nodes[0]


# ---------------------------------------------------------------------------
# Empty / trivial scripts
# ---------------------------------------------------------------------------


class TestEmpty:
    def test_empty_string(self):
        s = parse_string("")
        assert s.source == "<inline>"
        assert s.body == []

    def test_whitespace_only(self):
        s = parse_string("   \n\n   \n")
        assert s.body == []

    def test_comments_only(self):
        s = parse_string("-- comment 1\n-- comment 2\n")
        assert len(s.body) == 1
        assert isinstance(s.body[0], Comment)
        assert s.body[0].text == "-- comment 1\n-- comment 2"
        assert s.body[0].span.start_line == 1
        assert s.body[0].span.end_line == 2

    def test_block_comment_only(self):
        s = parse_string("/* block comment */\n")
        assert len(s.body) == 1
        assert isinstance(s.body[0], Comment)
        assert s.body[0].text == "/* block comment */"


# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------


class TestSqlStatements:
    def test_single_statement(self):
        node = _first("SELECT 1;")
        assert isinstance(node, SqlStatement)
        assert node.text == "SELECT 1;"
        assert node.span.start_line == 1

    def test_multi_line_statement(self):
        sql = "SELECT\n  col1,\n  col2\nFROM t;"
        node = _first(sql)
        assert isinstance(node, SqlStatement)
        assert "col1" in node.text
        assert "col2" in node.text
        assert node.span.start_line == 1
        assert node.span.effective_end_line == 4

    def test_multiple_statements(self):
        nodes = _body("SELECT 1;\nSELECT 2;")
        assert len(nodes) == 2
        assert all(isinstance(n, SqlStatement) for n in nodes)
        assert nodes[0].text == "SELECT 1;"
        assert nodes[1].text == "SELECT 2;"

    def test_statement_after_comment(self):
        nodes = _body("-- setup\nSELECT 1;")
        assert len(nodes) == 2
        assert isinstance(nodes[0], Comment)
        assert nodes[0].text == "-- setup"
        assert isinstance(nodes[1], SqlStatement)

    def test_semicolon_deduplication_not_done(self):
        # The AST parser preserves raw text; dedup is the executor's job
        node = _first("SELECT 1;;;")
        assert isinstance(node, SqlStatement)

    def test_line_continuation_backslash(self):
        sql = "SELECT \\\n  1;"
        node = _first(sql)
        assert isinstance(node, SqlStatement)

    def test_incomplete_sql_raises(self):
        with pytest.raises(ErrInfo, match="Incomplete SQL"):
            parse_string("SELECT 1")

    def test_incomplete_sql_inline_hint(self):
        with pytest.raises(ErrInfo, match="Metacommands must be prefixed"):
            parse_string("SELECT 1")

    def test_block_comment_preserved(self):
        nodes = _body("/* comment */\nSELECT 1;")
        assert len(nodes) == 2
        assert isinstance(nodes[0], Comment)
        assert nodes[0].text == "/* comment */"
        assert isinstance(nodes[1], SqlStatement)

    def test_multi_line_block_comment(self):
        nodes = _body("/*\n  multi-line\n  comment\n*/\nSELECT 1;")
        assert len(nodes) == 2
        assert isinstance(nodes[0], Comment)
        assert "multi-line" in nodes[0].text
        assert isinstance(nodes[1], SqlStatement)


# ---------------------------------------------------------------------------
# Metacommands (flat)
# ---------------------------------------------------------------------------


class TestMetaCommands:
    def test_simple_sub(self):
        node = _first("-- !x! SUB myvar = hello")
        assert isinstance(node, MetaCommandStatement)
        assert node.command == "SUB myvar = hello"
        assert node.span.start_line == 1

    def test_config_option(self):
        node = _first("-- !x! ERROR_HALT ON")
        assert isinstance(node, MetaCommandStatement)
        assert node.command == "ERROR_HALT ON"

    def test_mixed_sql_and_metacommands(self):
        script = "SELECT 1;\n-- !x! SUB x = 1\nSELECT 2;"
        nodes = _body(script)
        assert len(nodes) == 3
        assert isinstance(nodes[0], SqlStatement)
        assert isinstance(nodes[1], MetaCommandStatement)
        assert isinstance(nodes[2], SqlStatement)

    def test_metacommand_after_incomplete_sql_warns(self):
        # The parser should warn about incomplete SQL but continue
        # This mimics the old parser behavior
        script = "SELECT 1\n-- !x! SUB x = 1\nSELECT 2;"
        nodes = _body(script)
        # The incomplete SQL is dropped with a warning, metacommand and SQL remain
        assert len(nodes) == 2
        assert isinstance(nodes[0], MetaCommandStatement)
        assert isinstance(nodes[1], SqlStatement)


# ---------------------------------------------------------------------------
# IF / ELSEIF / ELSE / ENDIF
# ---------------------------------------------------------------------------


class TestIfBlock:
    def test_simple_if(self):
        script = "-- !x! IF (HAS_ROWS)\nSELECT 1;\n-- !x! ENDIF"
        node = _first(script)
        assert isinstance(node, IfBlock)
        assert node.condition == "HAS_ROWS"
        assert len(node.body) == 1
        assert isinstance(node.body[0], SqlStatement)
        assert node.else_body == []
        assert node.span.start_line == 1
        assert node.span.effective_end_line == 3

    def test_if_else(self):
        script = "-- !x! IF (HAS_ROWS)\nSELECT 1;\n-- !x! ELSE\nSELECT 2;\n-- !x! ENDIF"
        node = _first(script)
        assert isinstance(node, IfBlock)
        assert len(node.body) == 1
        assert len(node.else_body) == 1
        assert node.body[0].text == "SELECT 1;"
        assert node.else_body[0].text == "SELECT 2;"

    def test_if_elseif_else(self):
        script = (
            "-- !x! IF (HAS_ROWS)\n"
            "SELECT 1;\n"
            "-- !x! ELSEIF (ROW_COUNT_GT(5))\n"
            "SELECT 2;\n"
            "-- !x! ELSE\n"
            "SELECT 3;\n"
            "-- !x! ENDIF"
        )
        node = _first(script)
        assert isinstance(node, IfBlock)
        assert node.condition == "HAS_ROWS"
        assert len(node.body) == 1
        assert len(node.elseif_clauses) == 1
        assert node.elseif_clauses[0].condition == "ROW_COUNT_GT(5)"
        assert len(node.elseif_clauses[0].body) == 1
        assert len(node.else_body) == 1

    def test_multiple_elseif(self):
        script = (
            "-- !x! IF (COND_A)\n"
            "SELECT 1;\n"
            "-- !x! ELSEIF (COND_B)\n"
            "SELECT 2;\n"
            "-- !x! ELSEIF (COND_C)\n"
            "SELECT 3;\n"
            "-- !x! ENDIF"
        )
        node = _first(script)
        assert isinstance(node, IfBlock)
        assert len(node.elseif_clauses) == 2

    def test_inline_if(self):
        script = '-- !x! IF (HAS_ROWS) { LOG "found rows" }'
        node = _first(script)
        assert isinstance(node, IfBlock)
        assert node.condition == "HAS_ROWS"
        assert len(node.body) == 1
        assert isinstance(node.body[0], MetaCommandStatement)
        assert node.body[0].command == 'LOG "found rows"'

    def test_nested_if(self):
        script = "-- !x! IF (COND_A)\n-- !x! IF (COND_B)\nSELECT 1;\n-- !x! ENDIF\n-- !x! ENDIF"
        node = _first(script)
        assert isinstance(node, IfBlock)
        assert len(node.body) == 1
        inner = node.body[0]
        assert isinstance(inner, IfBlock)
        assert inner.condition == "COND_B"
        assert len(inner.body) == 1

    def test_unmatched_endif_raises(self):
        with pytest.raises(ErrInfo, match="ENDIF without matching IF"):
            parse_string("-- !x! ENDIF")

    def test_unmatched_else_raises(self):
        with pytest.raises(ErrInfo, match="ELSE without matching IF"):
            parse_string("-- !x! ELSE")

    def test_unmatched_elseif_raises(self):
        with pytest.raises(ErrInfo, match="ELSEIF without matching IF"):
            parse_string("-- !x! ELSEIF (COND)")

    def test_unclosed_if_raises(self):
        with pytest.raises(ErrInfo, match="Unmatched IF"):
            parse_string("-- !x! IF (HAS_ROWS)\nSELECT 1;")

    def test_orif_absorbed_as_condition_modifier(self):
        """ORIF compounds the IF condition — stored as a ConditionModifier."""
        script = "-- !x! IF (HAS_ROWS)\n-- !x! ORIF (OTHER_COND)\nSELECT 1;\n-- !x! ENDIF"
        node = _first(script)
        assert isinstance(node, IfBlock)
        assert len(node.condition_modifiers) == 1
        assert node.condition_modifiers[0].kind == "OR"
        assert node.condition_modifiers[0].condition == "OTHER_COND"
        # ORIF is not in the body — only the SELECT is
        assert len(node.body) == 1
        assert isinstance(node.body[0], SqlStatement)

    def test_andif_absorbed_as_condition_modifier(self):
        script = "-- !x! IF (HAS_ROWS)\n-- !x! ANDIF (OTHER_COND)\nSELECT 1;\n-- !x! ENDIF"
        node = _first(script)
        assert isinstance(node, IfBlock)
        assert len(node.condition_modifiers) == 1
        assert node.condition_modifiers[0].kind == "AND"
        assert node.condition_modifiers[0].condition == "OTHER_COND"
        assert len(node.body) == 1

    def test_multiple_modifiers(self):
        script = "-- !x! IF (COND_A)\n-- !x! ANDIF (COND_B)\n-- !x! ORIF (COND_C)\nSELECT 1;\n-- !x! ENDIF"
        node = _first(script)
        assert isinstance(node, IfBlock)
        assert len(node.condition_modifiers) == 2
        assert node.condition_modifiers[0].kind == "AND"
        assert node.condition_modifiers[1].kind == "OR"
        assert len(node.body) == 1

    def test_elseif_andif_modifier(self):
        """ANDIF after ELSEIF is stored on the ElseIfClause, not the IfBlock."""
        script = "-- !x! IF (COND_A)\nSELECT 1;\n-- !x! ELSEIF (COND_B)\n-- !x! ANDIF (COND_C)\nSELECT 2;\n-- !x! ENDIF"
        node = _first(script)
        assert isinstance(node, IfBlock)
        assert len(node.condition_modifiers) == 0
        assert len(node.elseif_clauses) == 1
        clause = node.elseif_clauses[0]
        assert clause.condition == "COND_B"
        assert len(clause.condition_modifiers) == 1
        assert clause.condition_modifiers[0].kind == "AND"
        assert clause.condition_modifiers[0].condition == "COND_C"
        assert len(clause.body) == 1

    def test_elseif_orif_modifier(self):
        """ORIF after ELSEIF is stored on the ElseIfClause."""
        script = "-- !x! IF (COND_A)\nSELECT 1;\n-- !x! ELSEIF (COND_B)\n-- !x! ORIF (COND_C)\nSELECT 2;\n-- !x! ENDIF"
        node = _first(script)
        assert isinstance(node, IfBlock)
        assert len(node.condition_modifiers) == 0
        clause = node.elseif_clauses[0]
        assert len(clause.condition_modifiers) == 1
        assert clause.condition_modifiers[0].kind == "OR"
        assert clause.condition_modifiers[0].condition == "COND_C"

    def test_elseif_multiple_modifiers(self):
        """Multiple ANDIF/ORIF after ELSEIF."""
        script = (
            "-- !x! IF (COND_A)\nSELECT 1;\n"
            "-- !x! ELSEIF (COND_B)\n-- !x! ANDIF (COND_C)\n-- !x! ORIF (COND_D)\nSELECT 2;\n"
            "-- !x! ENDIF"
        )
        node = _first(script)
        clause = node.elseif_clauses[0]
        assert len(clause.condition_modifiers) == 2
        assert clause.condition_modifiers[0].kind == "AND"
        assert clause.condition_modifiers[0].condition == "COND_C"
        assert clause.condition_modifiers[1].kind == "OR"
        assert clause.condition_modifiers[1].condition == "COND_D"

    def test_if_andif_then_elseif_andif(self):
        """ANDIF on IF stays on IF; ANDIF on ELSEIF stays on ELSEIF."""
        script = (
            "-- !x! IF (COND_A)\n-- !x! ANDIF (COND_B)\nSELECT 1;\n"
            "-- !x! ELSEIF (COND_C)\n-- !x! ANDIF (COND_D)\nSELECT 2;\n"
            "-- !x! ENDIF"
        )
        node = _first(script)
        assert isinstance(node, IfBlock)
        assert len(node.condition_modifiers) == 1
        assert node.condition_modifiers[0].condition == "COND_B"
        assert len(node.elseif_clauses) == 1
        clause = node.elseif_clauses[0]
        assert len(clause.condition_modifiers) == 1
        assert clause.condition_modifiers[0].condition == "COND_D"

    def test_andif_without_if_raises(self):
        with pytest.raises(ErrInfo, match="ANDIF without matching IF"):
            parse_string("-- !x! ANDIF (COND)")

    def test_orif_without_if_raises(self):
        with pytest.raises(ErrInfo, match="ORIF without matching IF"):
            parse_string("-- !x! ORIF (COND)")


# ---------------------------------------------------------------------------
# LOOP / ENDLOOP
# ---------------------------------------------------------------------------


class TestLoopBlock:
    def test_while_loop(self):
        script = "-- !x! LOOP WHILE (HAS_ROWS)\nSELECT 1;\n-- !x! ENDLOOP"
        node = _first(script)
        assert isinstance(node, LoopBlock)
        assert node.loop_type == "WHILE"
        assert node.condition == "HAS_ROWS"
        assert len(node.body) == 1
        assert node.span.start_line == 1
        assert node.span.effective_end_line == 3

    def test_until_loop(self):
        script = "-- !x! LOOP UNTIL (ROW_COUNT_EQ(0))\nDELETE FROM t LIMIT 100;\n-- !x! END LOOP"
        node = _first(script)
        assert isinstance(node, LoopBlock)
        assert node.loop_type == "UNTIL"

    def test_nested_loop(self):
        script = "-- !x! LOOP WHILE (COND_A)\n-- !x! LOOP UNTIL (COND_B)\nSELECT 1;\n-- !x! ENDLOOP\n-- !x! ENDLOOP"
        node = _first(script)
        assert isinstance(node, LoopBlock)
        assert len(node.body) == 1
        inner = node.body[0]
        assert isinstance(inner, LoopBlock)
        assert inner.loop_type == "UNTIL"

    def test_unmatched_endloop_raises(self):
        with pytest.raises(ErrInfo, match="ENDLOOP without matching LOOP"):
            parse_string("-- !x! ENDLOOP")

    def test_unclosed_loop_raises(self):
        with pytest.raises(ErrInfo, match="Unmatched LOOP"):
            parse_string("-- !x! LOOP WHILE (HAS_ROWS)\nSELECT 1;")

    def test_loop_with_metacommands(self):
        script = "-- !x! LOOP WHILE (HAS_ROWS)\n-- !x! SUB x = 1\nSELECT 1;\n-- !x! ENDLOOP"
        node = _first(script)
        assert isinstance(node, LoopBlock)
        assert len(node.body) == 2
        assert isinstance(node.body[0], MetaCommandStatement)
        assert isinstance(node.body[1], SqlStatement)


# ---------------------------------------------------------------------------
# BEGIN BATCH / END BATCH
# ---------------------------------------------------------------------------


class TestBatchBlock:
    def test_basic_batch(self):
        script = "-- !x! BEGIN BATCH\nINSERT INTO t VALUES (1);\nINSERT INTO t VALUES (2);\n-- !x! END BATCH"
        node = _first(script)
        assert isinstance(node, BatchBlock)
        assert len(node.body) == 2
        assert node.span.start_line == 1
        assert node.span.effective_end_line == 4

    def test_unmatched_end_batch_raises(self):
        with pytest.raises(ErrInfo, match="END BATCH without matching BEGIN BATCH"):
            parse_string("-- !x! END BATCH")

    def test_unclosed_batch_raises(self):
        with pytest.raises(ErrInfo, match="Unmatched BATCH"):
            parse_string("-- !x! BEGIN BATCH\nINSERT INTO t VALUES (1);")


# ---------------------------------------------------------------------------
# BEGIN SCRIPT / END SCRIPT
# ---------------------------------------------------------------------------


class TestScriptBlock:
    def test_basic_script(self):
        script = "-- !x! BEGIN SCRIPT my_proc\nSELECT 1;\n-- !x! END SCRIPT"
        node = _first(script)
        assert isinstance(node, ScriptBlock)
        assert node.name == "my_proc"
        assert node.param_names is None
        assert len(node.body) == 1

    def test_script_with_params(self):
        script = "-- !x! BEGIN SCRIPT load_data WITH PARAMETERS (table_name, file_path)\nSELECT 1;\n-- !x! END SCRIPT"
        node = _first(script)
        assert isinstance(node, ScriptBlock)
        assert node.param_names == ["table_name", "file_path"]

    def test_script_with_params_short(self):
        script = "-- !x! CREATE SCRIPT loader (tbl)\nSELECT 1;\n-- !x! END SCRIPT"
        node = _first(script)
        assert isinstance(node, ScriptBlock)
        assert node.param_names == ["tbl"]

    def test_named_end_script(self):
        script = "-- !x! BEGIN SCRIPT my_proc\nSELECT 1;\n-- !x! END SCRIPT my_proc"
        node = _first(script)
        assert isinstance(node, ScriptBlock)
        assert node.name == "my_proc"

    def test_mismatched_end_script_raises(self):
        with pytest.raises(ErrInfo, match="Mismatched script name"):
            parse_string("-- !x! BEGIN SCRIPT foo\nSELECT 1;\n-- !x! END SCRIPT bar")

    def test_unmatched_end_script_raises(self):
        with pytest.raises(ErrInfo, match="Unmatched END SCRIPT"):
            parse_string("-- !x! END SCRIPT")

    def test_unclosed_script_raises(self):
        with pytest.raises(ErrInfo, match="Unmatched SCRIPT"):
            parse_string("-- !x! BEGIN SCRIPT foo\nSELECT 1;")

    def test_invalid_params_raises(self):
        with pytest.raises(ErrInfo, match="Invalid BEGIN SCRIPT"):
            parse_string("-- !x! BEGIN SCRIPT foo INVALID SYNTAX\nSELECT 1;\n-- !x! END SCRIPT")

    def test_default_params(self):
        script = "-- !x! BEGIN SCRIPT loader(schema, batch=1000)\nSELECT 1;\n-- !x! END SCRIPT"
        node = _first(script)
        assert isinstance(node, ScriptBlock)
        assert node.param_names == ["schema", "batch"]
        assert node.param_defs[0].default is None
        assert node.param_defs[1].default == "1000"

    def test_all_optional_params(self):
        script = "-- !x! BEGIN SCRIPT loader(a=x, b=y)\nSELECT 1;\n-- !x! END SCRIPT"
        node = _first(script)
        assert node.param_defs[0].default == "x"
        assert node.param_defs[1].default == "y"

    def test_required_after_optional_raises(self):
        with pytest.raises(ErrInfo, match="Required parameter|required parameter"):
            parse_string("-- !x! BEGIN SCRIPT bad(a=1, b)\nSELECT 1;\n-- !x! END SCRIPT")

    def test_default_with_with_params_syntax(self):
        script = "-- !x! BEGIN SCRIPT loader WITH PARAMETERS (a, b=100)\nSELECT 1;\n-- !x! END SCRIPT"
        node = _first(script)
        assert node.param_defs[1].default == "100"

    def test_docstring_with_params_and_defaults(self):
        script = "-- !x! BEGIN SCRIPT proc(a, b=10)\n-- The docstring.\n\nSELECT 1;\n-- !x! END SCRIPT"
        node = _first(script)
        assert node.doc == "The docstring."
        assert node.param_defs[0].required is True
        assert node.param_defs[1].default == "10"

    def test_docstring_single_line(self):
        script = "-- !x! BEGIN SCRIPT proc\n-- This is the doc.\n\nSELECT 1;\n-- !x! END SCRIPT"
        node = _first(script)
        assert node.doc == "This is the doc."

    def test_docstring_multi_line(self):
        script = "-- !x! BEGIN SCRIPT proc\n-- Line one.\n-- Line two.\n\nSELECT 1;\n-- !x! END SCRIPT"
        node = _first(script)
        assert node.doc == "Line one.\nLine two."

    def test_docstring_blank_line_terminates(self):
        script = "-- !x! BEGIN SCRIPT proc\n-- Doc line.\n\n-- Not doc.\nSELECT 1;\n-- !x! END SCRIPT"
        node = _first(script)
        assert node.doc == "Doc line."

    def test_docstring_metacommand_terminates(self):
        script = "-- !x! BEGIN SCRIPT proc\n-- !x! SUB ~x 1\nSELECT 1;\n-- !x! END SCRIPT"
        node = _first(script)
        assert node.doc is None

    def test_no_docstring(self):
        script = "-- !x! BEGIN SCRIPT proc\nSELECT 1;\n-- !x! END SCRIPT"
        node = _first(script)
        assert node.doc is None

    def test_docstring_block_comment(self):
        script = "-- !x! BEGIN SCRIPT proc\n/* Block comment doc. */\n\nSELECT 1;\n-- !x! END SCRIPT"
        node = _first(script)
        assert node.doc == "Block comment doc."

    def test_docstring_multi_line_block_comment(self):
        script = "-- !x! BEGIN SCRIPT proc\n/* Line one\n   Line two */\n\nSELECT 1;\n-- !x! END SCRIPT"
        node = _first(script)
        assert "Line one" in node.doc
        assert "Line two" in node.doc

    def test_docstring_empty_comment_lines(self):
        """Bare -- lines act as paragraph separators in docstrings."""
        script = "-- !x! BEGIN SCRIPT proc\n-- Paragraph one.\n--\n-- Paragraph two.\n\nSELECT 1;\n-- !x! END SCRIPT"
        node = _first(script)
        assert "Paragraph one." in node.doc
        assert "Paragraph two." in node.doc
        lines = node.doc.split("\n")
        assert lines[1] == ""  # empty separator


# ---------------------------------------------------------------------------
# BEGIN SQL / END SQL
# ---------------------------------------------------------------------------


class TestSqlBlock:
    def test_basic_sql_block(self):
        script = "-- !x! BEGIN SQL\nSELECT\n  1;\n-- some mid comment\nSELECT 2;\n-- !x! END SQL"
        node = _first(script)
        assert isinstance(node, SqlBlock)
        assert len(node.body) == 1
        # All lines between BEGIN SQL and END SQL are concatenated as one SQL statement
        assert isinstance(node.body[0], SqlStatement)

    def test_unmatched_end_sql_raises(self):
        with pytest.raises(ErrInfo, match="Unmatched END SQL"):
            parse_string("-- !x! END SQL")


# ---------------------------------------------------------------------------
# INCLUDE
# ---------------------------------------------------------------------------


class TestInclude:
    def test_include_file(self):
        node = _first("-- !x! INCLUDE helpers.sql")
        assert isinstance(node, IncludeDirective)
        assert node.target == "helpers.sql"
        assert node.is_execute_script is False

    def test_include_if_exists(self):
        node = _first("-- !x! INCLUDE IF EXISTS optional.sql")
        assert isinstance(node, IncludeDirective)
        assert node.target == "optional.sql"


# ---------------------------------------------------------------------------
# EXECUTE SCRIPT / RUN SCRIPT
# ---------------------------------------------------------------------------


class TestExecuteScript:
    def test_basic_execute(self):
        node = _first("-- !x! EXECUTE SCRIPT my_proc")
        assert isinstance(node, IncludeDirective)
        assert node.target == "my_proc"
        assert node.is_execute_script is True
        assert node.arguments is None

    def test_run_script(self):
        node = _first("-- !x! RUN SCRIPT my_proc")
        assert isinstance(node, IncludeDirective)
        assert node.is_execute_script is True

    def test_exec_script(self):
        node = _first("-- !x! EXEC SCRIPT my_proc")
        assert isinstance(node, IncludeDirective)
        assert node.is_execute_script is True

    def test_execute_with_args(self):
        node = _first("-- !x! EXECUTE SCRIPT loader WITH ARGS (table=users, file='data.csv')")
        assert isinstance(node, IncludeDirective)
        assert node.target == "loader"
        assert node.arguments is not None
        assert "table=users" in node.arguments

    def test_execute_with_loop(self):
        node = _first("-- !x! EXECUTE SCRIPT processor WHILE (HAS_ROWS)")
        assert isinstance(node, IncludeDirective)
        assert node.loop_type == "WHILE"
        assert node.loop_condition == "HAS_ROWS"


# ---------------------------------------------------------------------------
# Complex / mixed scripts
# ---------------------------------------------------------------------------


class TestComplex:
    def test_mixed_script(self):
        script = (
            "-- Setup\n"
            "-- !x! SUB table = users\n"
            "CREATE TABLE !!$table!! (id INT);\n"
            "-- !x! IF (HAS_ROWS)\n"
            "SELECT * FROM !!$table!!;\n"
            "-- !x! ENDIF\n"
            "DROP TABLE !!$table!!;\n"
        )
        nodes = _body(script)
        assert len(nodes) == 5
        assert isinstance(nodes[0], Comment)  # -- Setup
        assert isinstance(nodes[1], MetaCommandStatement)  # SUB
        assert isinstance(nodes[2], SqlStatement)  # CREATE TABLE
        assert isinstance(nodes[3], IfBlock)  # IF block
        assert isinstance(nodes[4], SqlStatement)  # DROP TABLE

    def test_if_inside_loop(self):
        script = (
            "-- !x! LOOP WHILE (HAS_ROWS)\n"
            "-- !x! IF (ROW_COUNT_GT(0))\n"
            "DELETE FROM t LIMIT 100;\n"
            "-- !x! ENDIF\n"
            "-- !x! ENDLOOP"
        )
        node = _first(script)
        assert isinstance(node, LoopBlock)
        assert len(node.body) == 1
        assert isinstance(node.body[0], IfBlock)
        assert len(node.body[0].body) == 1

    def test_batch_inside_if(self):
        script = (
            "-- !x! IF (HAS_ROWS)\n"
            "-- !x! BEGIN BATCH\n"
            "INSERT INTO t VALUES (1);\n"
            "INSERT INTO t VALUES (2);\n"
            "-- !x! END BATCH\n"
            "-- !x! ENDIF"
        )
        node = _first(script)
        assert isinstance(node, IfBlock)
        assert len(node.body) == 1
        assert isinstance(node.body[0], BatchBlock)
        assert len(node.body[0].body) == 2

    def test_script_block_with_execute(self):
        script = (
            "-- !x! BEGIN SCRIPT loader (tbl)\n"
            "SELECT * FROM !!#tbl!!;\n"
            "-- !x! END SCRIPT\n"
            "-- !x! EXECUTE SCRIPT loader WITH ARGS (tbl=users)"
        )
        nodes = _body(script)
        assert len(nodes) == 2
        assert isinstance(nodes[0], ScriptBlock)
        assert isinstance(nodes[1], IncludeDirective)
        assert nodes[1].is_execute_script is True

    def test_walk_counts(self):
        script = (
            "-- !x! SUB x = 1\n"
            "-- !x! IF (HAS_ROWS)\n"
            "SELECT 1;\n"
            "-- !x! ELSE\n"
            "-- !x! LOOP WHILE (COND)\n"
            "INSERT INTO t VALUES (1);\n"
            "-- !x! ENDLOOP\n"
            "-- !x! ENDIF\n"
            "SELECT 2;\n"
        )
        s = parse_string(script)
        walked = list(s.walk())
        # SUB, IfBlock, SELECT 1, LoopBlock, INSERT, SELECT 2 = 6
        assert len(walked) == 6

    def test_source_name_propagates(self):
        script = parse_string("SELECT 1;", source_name="my_script.sql")
        assert script.source == "my_script.sql"
        assert script.body[0].span.file == "my_script.sql"


# ---------------------------------------------------------------------------
# Block comment edge cases
# ---------------------------------------------------------------------------


class TestBlockComments:
    def test_single_line_block_comment(self):
        nodes = _body("/* comment */\nSELECT 1;")
        assert len(nodes) == 2
        assert isinstance(nodes[0], Comment)
        assert isinstance(nodes[1], SqlStatement)

    def test_multi_line_block_comment(self):
        nodes = _body("/*\n  line 1\n  line 2\n*/\nSELECT 1;")
        assert len(nodes) == 2
        assert isinstance(nodes[0], Comment)
        assert nodes[0].span.start_line == 1
        assert nodes[0].span.end_line == 4
        assert isinstance(nodes[1], SqlStatement)

    def test_sql_after_block_comment(self):
        nodes = _body("/* skip this */\nSELECT 42;")
        assert len(nodes) == 2
        assert isinstance(nodes[0], Comment)
        assert nodes[0].text == "/* skip this */"
        assert nodes[1].text == "SELECT 42;"

    def test_consecutive_line_comments_grouped(self):
        """Multiple consecutive -- lines produce a single Comment node."""
        nodes = _body("-- line 1\n-- line 2\n-- line 3\nSELECT 1;")
        assert len(nodes) == 2
        assert isinstance(nodes[0], Comment)
        assert nodes[0].text == "-- line 1\n-- line 2\n-- line 3"
        assert nodes[0].span.start_line == 1
        assert nodes[0].span.end_line == 3
        assert isinstance(nodes[1], SqlStatement)

    def test_blank_line_splits_comment_groups(self):
        """A blank line between -- comments produces two separate Comment nodes."""
        nodes = _body("-- group 1\n\n-- group 2\nSELECT 1;")
        assert len(nodes) == 3
        assert isinstance(nodes[0], Comment)
        assert nodes[0].text == "-- group 1"
        assert isinstance(nodes[1], Comment)
        assert nodes[1].text == "-- group 2"
        assert isinstance(nodes[2], SqlStatement)

    def test_metacommand_splits_comment_groups(self):
        """A metacommand between -- comments produces separate Comment nodes."""
        nodes = _body("-- header\n-- !x! SUB x = 1\n-- footer\nSELECT 1;")
        assert len(nodes) == 4
        assert isinstance(nodes[0], Comment)
        assert nodes[0].text == "-- header"
        assert isinstance(nodes[1], MetaCommandStatement)
        assert isinstance(nodes[2], Comment)
        assert nodes[2].text == "-- footer"
        assert isinstance(nodes[3], SqlStatement)


# ---------------------------------------------------------------------------
# INCLUDE IF EXISTS
# ---------------------------------------------------------------------------


class TestIncludeIfExists:
    def test_include_if_exists_flag(self):
        node = _first("-- !x! INCLUDE IF EXISTS optional.sql")
        assert isinstance(node, IncludeDirective)
        assert node.target == "optional.sql"
        assert node.if_exists is True

    def test_include_without_if_exists(self):
        node = _first("-- !x! INCLUDE required.sql")
        assert isinstance(node, IncludeDirective)
        assert node.if_exists is False

    def test_execute_script_if_exists(self):
        node = _first("-- !x! EXECUTE SCRIPT IF EXISTS loader")
        assert isinstance(node, IncludeDirective)
        assert node.target == "loader"
        assert node.if_exists is True
        assert node.is_execute_script is True

    def test_execute_script_without_if_exists(self):
        node = _first("-- !x! EXECUTE SCRIPT loader")
        assert isinstance(node, IncludeDirective)
        assert node.if_exists is False


# ---------------------------------------------------------------------------
# ROLLBACK / BREAK / special metacommands
# ---------------------------------------------------------------------------


class TestFlatControlMetacommands:
    """Metacommands that are NOT block-openers but have control semantics.

    These are stored as flat MetaCommandStatement nodes in the AST —
    their runtime behavior is handled by the executor, not the parser.
    """

    def test_rollback(self):
        node = _first("-- !x! ROLLBACK")
        assert isinstance(node, MetaCommandStatement)
        assert node.command == "ROLLBACK"

    def test_rollback_batch(self):
        node = _first("-- !x! ROLLBACK BATCH")
        assert isinstance(node, MetaCommandStatement)
        assert "ROLLBACK" in node.command

    def test_break_inside_loop(self):
        script = "-- !x! LOOP WHILE (HAS_ROWS)\n-- !x! BREAK\n-- !x! ENDLOOP"
        node = _first(script)
        assert isinstance(node, LoopBlock)
        assert len(node.body) == 1
        assert isinstance(node.body[0], MetaCommandStatement)
        assert node.body[0].command == "BREAK"

    def test_error_halt_on_off(self):
        node = _first("-- !x! ERROR_HALT ON")
        assert isinstance(node, MetaCommandStatement)
        assert node.command == "ERROR_HALT ON"

    def test_on_error_halt_execute_script(self):
        """ON ERROR_HALT EXECUTE SCRIPT is a handler registration — flat metacommand."""
        node = _first("-- !x! ON ERROR_HALT EXECUTE SCRIPT cleanup")
        assert isinstance(node, MetaCommandStatement)
        assert "ON ERROR_HALT" in node.command

    def test_on_cancel_halt_execute_script(self):
        node = _first("-- !x! ON CANCEL_HALT EXECUTE SCRIPT cleanup")
        assert isinstance(node, MetaCommandStatement)
        assert "ON CANCEL_HALT" in node.command

    def test_assert(self):
        node = _first('-- !x! ASSERT EQUALS(!!x!!, 1) "x should be 1"')
        assert isinstance(node, MetaCommandStatement)
        assert "ASSERT" in node.command

    def test_wait_until(self):
        node = _first("-- !x! WAIT_UNTIL TABLE_EXISTS(t) HALT AFTER 30 SECONDS")
        assert isinstance(node, MetaCommandStatement)
        assert "WAIT_UNTIL" in node.command


# ---------------------------------------------------------------------------
# BEGIN SQL edge cases
# ---------------------------------------------------------------------------


class TestSqlBlockEdgeCases:
    def test_metacommands_inside_sql_block_are_dropped(self):
        """Metacommands inside BEGIN SQL are silently dropped (matches old parser)."""
        script = "-- !x! BEGIN SQL\nSELECT 1\n-- !x! SUB x = 1\nFROM t;\n-- !x! END SQL"
        node = _first(script)
        assert isinstance(node, SqlBlock)
        assert len(node.body) == 1
        sql = node.body[0]
        assert isinstance(sql, SqlStatement)
        # The metacommand line should NOT appear in the SQL text
        assert "SUB" not in sql.text
        # But the SQL before and after should be there
        assert "SELECT 1" in sql.text
        assert "FROM t;" in sql.text

    def test_comments_inside_sql_block_are_accumulated(self):
        """Regular comments (not metacommands) inside SQL blocks are SQL text."""
        script = "-- !x! BEGIN SQL\nSELECT 1\n-- this is a SQL comment\nFROM t;\n-- !x! END SQL"
        node = _first(script)
        assert isinstance(node, SqlBlock)
        sql = node.body[0]
        assert "this is a SQL comment" in sql.text

    def test_sql_block_preserves_semicolons(self):
        """Intermediate semicolons inside BEGIN SQL don't split statements."""
        script = (
            "-- !x! BEGIN SQL\n"
            "CREATE FUNCTION f() RETURNS void AS $$\n"
            "BEGIN\n"
            "  INSERT INTO t VALUES (1);\n"
            "  INSERT INTO t VALUES (2);\n"
            "END;\n"
            "$$ LANGUAGE plpgsql;\n"
            "-- !x! END SQL"
        )
        node = _first(script)
        assert isinstance(node, SqlBlock)
        # Everything should be one big SQL statement
        assert len(node.body) == 1


# ---------------------------------------------------------------------------
# Nesting edge cases
# ---------------------------------------------------------------------------


class TestNestingEdgeCases:
    def test_if_inside_batch(self):
        script = "-- !x! BEGIN BATCH\n-- !x! IF (HAS_ROWS)\nINSERT INTO t VALUES (1);\n-- !x! ENDIF\n-- !x! END BATCH"
        node = _first(script)
        assert isinstance(node, BatchBlock)
        assert len(node.body) == 1
        assert isinstance(node.body[0], IfBlock)

    def test_loop_inside_if_inside_loop(self):
        script = (
            "-- !x! LOOP WHILE (COND_A)\n"
            "-- !x! IF (COND_B)\n"
            "-- !x! LOOP UNTIL (COND_C)\n"
            "SELECT 1;\n"
            "-- !x! ENDLOOP\n"
            "-- !x! ENDIF\n"
            "-- !x! ENDLOOP"
        )
        outer = _first(script)
        assert isinstance(outer, LoopBlock)
        inner_if = outer.body[0]
        assert isinstance(inner_if, IfBlock)
        inner_loop = inner_if.body[0]
        assert isinstance(inner_loop, LoopBlock)
        assert inner_loop.loop_type == "UNTIL"

    def test_wrong_block_close_order_raises(self):
        """Closing blocks in wrong order should raise."""
        with pytest.raises(ErrInfo):
            parse_string(
                "-- !x! IF (HAS_ROWS)\n"
                "-- !x! BEGIN BATCH\n"
                "SELECT 1;\n"
                "-- !x! ENDIF\n"  # should be END BATCH first
                "-- !x! END BATCH",
            )

    def test_script_block_inside_if(self):
        script = "-- !x! IF (HAS_ROWS)\n-- !x! BEGIN SCRIPT inner_proc\nSELECT 1;\n-- !x! END SCRIPT\n-- !x! ENDIF"
        node = _first(script)
        assert isinstance(node, IfBlock)
        assert len(node.body) == 1
        assert isinstance(node.body[0], ScriptBlock)
