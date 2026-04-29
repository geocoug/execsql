"""Tests for the execsql LSP analysis, hover, and completion modules.

These tests exercise the LSP logic without needing pygls or a running
language server — they test the pure Python analysis and generation
functions directly.
"""

from __future__ import annotations

from execsql.lsp.analysis import analyze_document
from execsql.lsp.completions import get_completions
from execsql.lsp.hover import get_hover


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


class TestAnalysis:
    def test_valid_script_no_diagnostics(self):
        result = analyze_document("test.sql", "SELECT 1;")
        assert result.script is not None
        assert result.parse_error is None
        # May have lint warnings (undefined vars, missing includes) but no errors
        errors = [d for d in result.diagnostics if d[0] == "error"]
        assert errors == []

    def test_parse_error_produces_diagnostic(self):
        result = analyze_document("test.sql", "-- !x! IF (TRUE)\nSELECT 1;")
        assert result.parse_error is not None
        assert len(result.diagnostics) >= 1
        assert result.diagnostics[0][0] == "error"

    def test_extracts_script_blocks(self):
        source = "-- !x! BEGIN SCRIPT my_proc\nSELECT 1;\n-- !x! END SCRIPT"
        result = analyze_document("test.sql", source)
        assert "my_proc" in result.script_blocks
        assert result.script_blocks["my_proc"].start_line == 1

    def test_extracts_variables(self):
        source = "-- !x! SUB greeting hello\n-- !x! SUB_ADD counter 1"
        result = analyze_document("test.sql", source)
        assert "greeting" in result.defined_vars
        assert "counter" in result.defined_vars
        assert result.defined_vars["greeting"] == 1
        assert result.defined_vars["counter"] == 2

    def test_builds_symbols(self):
        source = (
            "-- !x! BEGIN SCRIPT loader (tbl)\n"
            "SELECT 1;\n"
            "-- !x! END SCRIPT\n"
            "-- !x! IF (TRUE)\n"
            "SELECT 2;\n"
            "-- !x! ENDIF\n"
        )
        result = analyze_document("test.sql", source)
        assert len(result.symbols) == 2
        assert result.symbols[0].kind == "script"
        assert "loader" in result.symbols[0].name
        assert result.symbols[1].kind == "if"

    def test_empty_script(self):
        result = analyze_document("test.sql", "-- just a comment\n")
        assert result.script is not None
        assert result.parse_error is None

    def test_nested_symbols(self):
        source = "-- !x! LOOP WHILE (TRUE)\n-- !x! IF (HAS_ROWS)\nSELECT 1;\n-- !x! ENDIF\n-- !x! ENDLOOP\n"
        result = analyze_document("test.sql", source)
        assert len(result.symbols) == 1
        assert result.symbols[0].kind == "loop"
        assert len(result.symbols[0].children) == 1
        assert result.symbols[0].children[0].kind == "if"


# ---------------------------------------------------------------------------
# Hover
# ---------------------------------------------------------------------------


class TestHover:
    def test_hover_metacommand_keyword(self):
        h = get_hover("-- !x! EXPORT QUERY <<SELECT 1>> TO CSV out.csv", 10)
        assert h is not None
        assert "EXPORT" in h

    def test_hover_if_keyword(self):
        h = get_hover("-- !x! IF (HAS_ROWS)", 10)
        assert h is not None
        assert "IF" in h

    def test_hover_sub_keyword(self):
        h = get_hover("-- !x! SUB myvar hello", 10)
        assert h is not None

    def test_hover_variable_reference(self):
        h = get_hover("INSERT INTO t VALUES ('!!myvar!!');", 25)
        assert h is not None
        assert "myvar" in h

    def test_hover_system_variable(self):
        h = get_hover("-- !x! WRITE '!!$CURRENT_TIME!!'", 20)
        assert h is not None
        assert "system variable" in h.lower() or "CURRENT_TIME" in h

    def test_hover_env_variable(self):
        h = get_hover("-- !x! SUB home !!&HOME!!", 20)
        assert h is not None
        assert "Environment" in h

    def test_hover_no_content_on_plain_sql(self):
        h = get_hover("SELECT * FROM users;", 5)
        assert h is None

    def test_hover_with_analysis_shows_definition_line(self):
        analysis = analyze_document("test.sql", "-- !x! SUB myvar hello\nSELECT '!!myvar!!';")
        h = get_hover("SELECT '!!myvar!!';", 12, analysis)
        assert h is not None
        assert "line 1" in h


# ---------------------------------------------------------------------------
# Completions
# ---------------------------------------------------------------------------


class TestCompletions:
    def test_keyword_completion(self):
        items = get_completions("-- !x! EX", 9)
        labels = [i["label"] for i in items]
        assert any("EXPORT" in lbl for lbl in labels)
        assert any("EXECUTE" in lbl for lbl in labels)

    def test_keyword_completion_case_insensitive(self):
        items = get_completions("-- !x! ex", 9)
        labels = [i["label"] for i in items]
        assert any("EXPORT" in lbl for lbl in labels)

    def test_keyword_completion_sub(self):
        items = get_completions("-- !x! SU", 9)
        labels = [i["label"] for i in items]
        assert any("SUB" in lbl for lbl in labels)

    def test_no_completions_on_plain_sql(self):
        items = get_completions("SELECT * FROM ", 14)
        assert items == []

    def test_variable_completion(self):
        analysis = analyze_document("test.sql", "-- !x! SUB myvar hello\n")
        items = get_completions("SELECT '!!", 10, analysis)
        labels = [i["label"] for i in items]
        assert any("myvar" in lbl for lbl in labels)

    def test_condition_completion_in_if(self):
        items = get_completions("-- !x! IF (", 11)
        labels = [i["label"] for i in items]
        assert any("HAS_ROWS" in lbl or "TABLE_EXISTS" in lbl for lbl in labels)

    def test_condition_completion_in_loop(self):
        items = get_completions("-- !x! LOOP WHILE (", 19)
        labels = [i["label"] for i in items]
        assert len(labels) > 0

    def test_empty_prefix_shows_all(self):
        items = get_completions("-- !x! ", 7)
        assert len(items) > 10  # should show many keywords
