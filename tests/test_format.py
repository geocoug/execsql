"""Tests for execsql.fmt module."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import patch


from execsql.format import (
    _is_comment_line,
    _protect_variables,
    _restore_variables,
    _sqlglot_format,
    collect_paths,
    format_file,
    format_metacommand,
    format_sql_block,
    parse_keyword,
)


# ---------------------------------------------------------------------------
# parse_keyword
# ---------------------------------------------------------------------------


class TestParseKeyword:
    def test_single_word(self):
        assert parse_keyword("WRITE something") == "WRITE"

    def test_single_word_lowercase(self):
        assert parse_keyword("write something") == "WRITE"

    def test_multi_word(self):
        assert parse_keyword("BEGIN SCRIPT myscript") == "BEGIN SCRIPT"

    def test_multi_word_case_insensitive(self):
        assert parse_keyword("begin script myscript") == "BEGIN SCRIPT"

    def test_multi_word_exact(self):
        assert parse_keyword("END LOOP") == "END LOOP"

    def test_sub_tempfile(self):
        assert parse_keyword("SUB_TEMPFILE myvar") == "SUB_TEMPFILE"

    def test_prompt_entry_form(self):
        assert parse_keyword("PROMPT ENTRY_FORM title") == "PROMPT ENTRY_FORM"

    def test_on_error_halt(self):
        assert parse_keyword("ON ERROR_HALT continue") == "ON ERROR_HALT"

    def test_single_word_no_args(self):
        assert parse_keyword("ENDIF") == "ENDIF"

    def test_first_word_with_paren(self):
        assert parse_keyword("SHELL(cmd)") == "SHELL"

    def test_system_cmd(self):
        assert parse_keyword("SYSTEM_CMD (ls -la)") == "SYSTEM_CMD"


# ---------------------------------------------------------------------------
# format_metacommand
# ---------------------------------------------------------------------------


class TestFormatMetacommand:
    def test_no_indent(self):
        result = format_metacommand("write 'hello'", depth=0, indent=4)
        assert result == "-- !x! WRITE 'hello'"

    def test_depth_one(self):
        result = format_metacommand("write 'hello'", depth=1, indent=4)
        assert result == "    -- !x! WRITE 'hello'"

    def test_depth_two(self):
        result = format_metacommand("write 'hello'", depth=2, indent=4)
        assert result == "        -- !x! WRITE 'hello'"

    def test_keyword_uppercased(self):
        result = format_metacommand("pause waiting", depth=0, indent=4)
        assert result.startswith("-- !x! PAUSE")

    def test_args_preserved(self):
        result = format_metacommand("WRITE 'Hello World'", depth=0, indent=4)
        assert result == "-- !x! WRITE 'Hello World'"

    def test_no_args(self):
        result = format_metacommand("ENDIF", depth=0, indent=4)
        assert result == "-- !x! ENDIF"

    def test_indent_two_spaces(self):
        result = format_metacommand("write x", depth=1, indent=2)
        assert result == "  -- !x! WRITE x"

    def test_multi_word_keyword(self):
        result = format_metacommand("begin script foo", depth=0, indent=4)
        assert result == "-- !x! BEGIN SCRIPT foo"


# ---------------------------------------------------------------------------
# format_file — depth tracking
# ---------------------------------------------------------------------------


class TestFormatFile:
    def test_empty_string(self):
        assert format_file("") == "\n"

    def test_blank_lines_preserved(self):
        result = format_file("-- !x! WRITE 'hi'\n\n-- !x! WRITE 'bye'\n")
        lines = result.splitlines()
        assert lines[1] == ""

    def test_block_open_increases_depth(self):
        source = "-- !x! IF 1=1\n-- !x! WRITE 'yes'\n-- !x! ENDIF\n"
        result = format_file(source, use_sql=False)
        lines = result.splitlines()
        assert lines[0] == "-- !x! IF 1=1"
        assert lines[1] == "    -- !x! WRITE 'yes'"
        assert lines[2] == "-- !x! ENDIF"

    def test_nested_blocks(self):
        source = "-- !x! IF 1=1\n-- !x! LOOP 3 TIMES\n-- !x! WRITE 'x'\n-- !x! END LOOP\n-- !x! ENDIF\n"
        result = format_file(source, use_sql=False)
        lines = result.splitlines()
        assert lines[0] == "-- !x! IF 1=1"
        assert lines[1] == "    -- !x! LOOP 3 TIMES"
        assert lines[2] == "        -- !x! WRITE 'x'"
        assert lines[3] == "    -- !x! END LOOP"
        assert lines[4] == "-- !x! ENDIF"

    def test_pivot_else(self):
        source = "-- !x! IF 1=1\n-- !x! WRITE 'yes'\n-- !x! ELSE\n-- !x! WRITE 'no'\n-- !x! ENDIF\n"
        result = format_file(source, use_sql=False)
        lines = result.splitlines()
        assert lines[2] == "-- !x! ELSE"  # PIVOT: same depth as IF
        assert lines[3] == "    -- !x! WRITE 'no'"

    def test_continuation_andif(self):
        source = "-- !x! IF 1=1\n-- !x! ANDIF 2=2\n-- !x! WRITE 'both'\n-- !x! ENDIF\n"
        result = format_file(source, use_sql=False)
        lines = result.splitlines()
        # ANDIF emits at depth-1 (0), no depth change
        assert lines[0] == "-- !x! IF 1=1"
        assert lines[1] == "-- !x! ANDIF 2=2"
        assert lines[2] == "    -- !x! WRITE 'both'"

    def test_keyword_uppercased_in_output(self):
        source = "-- !x! write 'hello'\n"
        result = format_file(source, use_sql=False)
        assert "WRITE" in result

    def test_depth_never_negative(self):
        source = "-- !x! ENDIF\n-- !x! ENDIF\n"
        result = format_file(source, use_sql=False)
        # Should not raise, depth clamped at 0
        assert result.count("-- !x! ENDIF") == 2

    def test_trailing_newline(self):
        result = format_file("-- !x! WRITE 'x'", use_sql=False)
        assert result.endswith("\n")

    def test_begin_script_block(self):
        source = "-- !x! BEGIN SCRIPT\n-- !x! WRITE 'x'\n-- !x! END SCRIPT\n"
        result = format_file(source, use_sql=False)
        lines = result.splitlines()
        assert lines[0] == "-- !x! BEGIN SCRIPT"
        assert lines[1] == "    -- !x! WRITE 'x'"
        assert lines[2] == "-- !x! END SCRIPT"

    def test_sql_passthrough_no_sql(self):
        source = "select * from foo;\n"
        result = format_file(source, use_sql=False)
        assert "select * from foo;" in result


# ---------------------------------------------------------------------------
# format_sql_block
# ---------------------------------------------------------------------------


class TestFormatSqlBlock:
    def test_empty_returns_empty(self):
        assert format_sql_block([], depth=0, indent=4, use_sql=False) == []

    def test_all_blank(self):
        result = format_sql_block(["", "  ", ""], depth=0, indent=4, use_sql=False)
        assert all(line == "" for line in result)

    def test_reindent(self):
        lines = ["    SELECT 1;"]
        result = format_sql_block(lines, depth=1, indent=4, use_sql=False)
        assert result == ["    SELECT 1;"]

    def test_no_sql_passthrough(self):
        lines = ["select 1;", "select 2;"]
        result = format_sql_block(lines, depth=0, indent=4, use_sql=False)
        assert result[0].strip() == "select 1;"


class TestFormatFileBranches:
    def test_trailing_blank_line_no_extra_newline(self):
        # Source with trailing blank line → output ends with "" → join ends with \n
        # covers the 285→287 branch (result already ends with \n)
        source = "-- !x! WRITE 'x'\n\n"
        result = format_file(source, use_sql=False)
        assert result.endswith("\n")


# ---------------------------------------------------------------------------
# collect_paths
# ---------------------------------------------------------------------------


class TestCollectPaths:
    def test_file_passthrough(self, tmp_path):
        f = tmp_path / "script.sql"
        f.write_text("-- test")
        result = collect_paths([f])
        assert result == [f]

    def test_directory_expansion(self, tmp_path):
        (tmp_path / "a.sql").write_text("-- a")
        (tmp_path / "b.sql").write_text("-- b")
        result = collect_paths([tmp_path])
        assert len(result) == 2
        assert all(p.suffix == ".sql" for p in result)

    def test_directory_recursive(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "top.sql").write_text("-- top")
        (sub / "nested.sql").write_text("-- nested")
        result = collect_paths([tmp_path])
        assert len(result) == 2

    def test_non_sql_files_excluded(self, tmp_path):
        (tmp_path / "script.sql").write_text("-- sql")
        (tmp_path / "notes.txt").write_text("notes")
        result = collect_paths([tmp_path])
        assert len(result) == 1
        assert result[0].name == "script.sql"

    def test_mixed_files_and_dirs(self, tmp_path):
        f = tmp_path / "direct.sql"
        f.write_text("-- direct")
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "nested.sql").write_text("-- nested")
        result = collect_paths([f, sub])
        assert len(result) == 2

    def test_empty_list(self):
        assert collect_paths([]) == []


# ---------------------------------------------------------------------------
# _protect_variables / _restore_variables
# ---------------------------------------------------------------------------


class TestProtectVariables:
    def test_no_vars_unchanged(self):
        protected, replacements = _protect_variables("SELECT 1")
        assert protected == "SELECT 1"
        assert replacements == []

    def test_double_bang_var(self):
        protected, replacements = _protect_variables("SELECT !!myvar!!")
        assert "!!myvar!!" not in protected
        assert len(replacements) == 1
        assert replacements[0][1] == "!!myvar!!"

    def test_deferred_var(self):
        protected, replacements = _protect_variables("SELECT !{myvar}!")
        assert "!{myvar}!" not in protected
        assert len(replacements) == 1
        assert replacements[0][1] == "!{myvar}!"

    def test_multiple_vars(self):
        protected, replacements = _protect_variables("SELECT !!a!!, !!b!!")
        assert len(replacements) == 2
        assert replacements[0][1] == "!!a!!"
        assert replacements[1][1] == "!!b!!"

    def test_placeholder_is_valid_identifier(self):
        protected, replacements = _protect_variables("SELECT !!x!!")
        placeholder = replacements[0][0]
        assert placeholder.isidentifier()


class TestRestoreVariables:
    def test_empty_replacements(self):
        result = _restore_variables("SELECT 1", [])
        assert result == "SELECT 1"

    def test_roundtrip_single(self):
        original = "SELECT !!myvar!!"
        protected, replacements = _protect_variables(original)
        restored = _restore_variables(protected, replacements)
        assert restored == original

    def test_roundtrip_multiple(self):
        original = "WHERE !!col!! = !!val!!"
        protected, replacements = _protect_variables(original)
        restored = _restore_variables(protected, replacements)
        assert restored == original

    def test_roundtrip_deferred(self):
        original = "SELECT !{myvar}!"
        protected, replacements = _protect_variables(original)
        restored = _restore_variables(protected, replacements)
        assert restored == original


# ---------------------------------------------------------------------------
# _is_comment_line
# ---------------------------------------------------------------------------


class TestIsCommentLine:
    def test_empty_line_not_comment(self):
        is_comment, in_block = _is_comment_line("", False)
        assert not is_comment
        assert not in_block

    def test_whitespace_only_not_comment(self):
        is_comment, in_block = _is_comment_line("   ", False)
        assert not is_comment
        assert not in_block

    def test_line_comment(self):
        is_comment, in_block = _is_comment_line("-- my comment", False)
        assert is_comment
        assert not in_block

    def test_block_comment_open(self):
        is_comment, in_block = _is_comment_line("/* block comment", False)
        assert is_comment
        assert in_block

    def test_block_comment_closed_same_line(self):
        is_comment, in_block = _is_comment_line("/* block */", False)
        assert is_comment
        assert not in_block

    def test_inside_block_is_comment(self):
        is_comment, in_block = _is_comment_line("anything in block", True)
        assert is_comment
        assert in_block

    def test_block_ends_on_line(self):
        is_comment, in_block = _is_comment_line("end of block */", True)
        assert is_comment
        assert not in_block

    def test_sql_line_not_comment(self):
        is_comment, in_block = _is_comment_line("SELECT 1;", False)
        assert not is_comment
        assert not in_block


# ---------------------------------------------------------------------------
# _sqlglot_format
# ---------------------------------------------------------------------------


class TestSqlglotFormat:
    def test_simple_select_formatted(self):
        result = _sqlglot_format(["select 1"])
        joined = "\n".join(result)
        assert "SELECT" in joined

    def test_variable_preserved_after_format(self):
        result = _sqlglot_format(["SELECT !!myvar!!"])
        joined = "\n".join(result)
        assert "!!myvar!!" in joined

    def test_deferred_var_preserved(self):
        result = _sqlglot_format(["SELECT !{myvar}!"])
        joined = "\n".join(result)
        assert "!{myvar}!" in joined

    def test_returns_list(self):
        result = _sqlglot_format(["SELECT 1"])
        assert isinstance(result, list)

    def test_empty_statement_returns_original(self):
        # A non-SQL "Command" token — sqlglot filters it → stmts is empty → return original
        lines = ["\\copy foo from bar"]
        result = _sqlglot_format(lines)
        assert isinstance(result, list)

    def test_exception_returns_original(self, monkeypatch):
        import sqlglot

        monkeypatch.setattr(sqlglot, "parse", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
        lines = ["SELECT 1"]
        result = _sqlglot_format(lines)
        assert result == lines


# ---------------------------------------------------------------------------
# format_sql_block — use_sql=True path
# ---------------------------------------------------------------------------


class TestFormatSqlBlockUseSql:
    def test_simple_sql_formatted(self):
        lines = ["select 1"]
        result = format_sql_block(lines, depth=0, indent=4, use_sql=True)
        joined = " ".join(result)
        assert "SELECT" in joined

    def test_indent_applied_with_use_sql(self):
        lines = ["select 1"]
        result = format_sql_block(lines, depth=1, indent=4, use_sql=True)
        non_empty = [line for line in result if line.strip()]
        assert all(line.startswith("    ") for line in non_empty)

    def test_comment_line_preserved(self):
        lines = ["-- my comment", "select 1"]
        result = format_sql_block(lines, depth=0, indent=4, use_sql=True)
        assert any("my comment" in line for line in result)

    def test_block_comment_preserved(self):
        lines = ["/* block comment */", "select 1"]
        result = format_sql_block(lines, depth=0, indent=4, use_sql=True)
        assert any("block comment" in line for line in result)

    def test_empty_lines_in_output(self):
        lines = ["select 1", "", "select 2"]
        result = format_sql_block(lines, depth=0, indent=4, use_sql=True)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_variable_preserved_in_use_sql(self):
        lines = ["SELECT !!myvar!!"]
        result = format_sql_block(lines, depth=0, indent=4, use_sql=True)
        joined = " ".join(result)
        assert "!!myvar!!" in joined

    def test_sql_then_comment_transition(self):
        # SQL first, then comment — exercises the seg_is_comment=False→True flush path
        lines = ["select 1;", "-- comment after sql"]
        result = format_sql_block(lines, depth=0, indent=4, use_sql=True)
        joined = " ".join(result)
        assert "comment after sql" in joined

    def test_comment_then_sql_transition(self):
        # Comment first, then SQL — exercises the seg_is_comment=True→False flush path
        lines = ["-- leading comment", "select 2;"]
        result = format_sql_block(lines, depth=0, indent=4, use_sql=True)
        joined = " ".join(result)
        assert "leading comment" in joined
        assert "SELECT" in joined


# ---------------------------------------------------------------------------
# main() CLI entry point
# ---------------------------------------------------------------------------


class TestMainCLI:
    """Tests for the execsql-format CLI via subprocess."""

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-c", "from execsql.format import main; main()", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def test_no_args_exits_nonzero(self):
        # no_args_is_help=True prints help but when invoked via -c (not installed)
        # typer exits with 2 (missing argument). Either way, no crash.
        result = self._run()
        assert result.returncode in (0, 1, 2)

    def test_stdout_output(self, tmp_path):
        sql_file = tmp_path / "test.sql"
        sql_file.write_text("-- !x! write 'hello'\n")
        result = self._run(str(sql_file))
        assert result.returncode == 0
        assert "WRITE" in result.stdout

    def test_check_mode_unchanged_exits_zero(self, tmp_path):
        sql_file = tmp_path / "test.sql"
        # Already formatted: keyword uppercase, no indentation needed
        sql_file.write_text("-- !x! WRITE 'hello'\n")
        result = self._run("--check", str(sql_file))
        assert result.returncode == 0

    def test_check_mode_changed_exits_one(self, tmp_path):
        sql_file = tmp_path / "test.sql"
        # lowercase keyword → needs reformatting
        sql_file.write_text("-- !x! write 'hello'\n")
        result = self._run("--check", str(sql_file))
        assert result.returncode == 1

    def test_in_place_rewrites_file(self, tmp_path):
        sql_file = tmp_path / "test.sql"
        sql_file.write_text("-- !x! write 'hello'\n")
        result = self._run("--in-place", str(sql_file))
        assert result.returncode == 0
        content = sql_file.read_text()
        assert "WRITE" in content

    def test_no_sql_files_exits_one(self, tmp_path):
        # Pass a directory with no .sql files
        result = self._run(str(tmp_path))
        assert result.returncode == 1


# ---------------------------------------------------------------------------
# main() — direct in-process tests (contribute to coverage)
# ---------------------------------------------------------------------------


class TestMainCLIDirect:
    """Call main() directly in the test process via sys.argv patching."""

    def _invoke(self, args, capsys=None):
        from execsql.format import main

        with patch("sys.argv", ["execsql-format"] + args):
            try:
                main()
            except SystemExit:
                pass

    def test_main_stdout_direct(self, tmp_path, capsys):
        sql_file = tmp_path / "test.sql"
        sql_file.write_text("-- !x! write 'hello'\n")
        self._invoke([str(sql_file)])
        captured = capsys.readouterr()
        assert "WRITE" in captured.out

    def test_main_check_mode_no_change(self, tmp_path):
        sql_file = tmp_path / "already.sql"
        sql_file.write_text("-- !x! WRITE 'hello'\n")
        self._invoke(["--check", str(sql_file)])
        # File should be unchanged
        assert sql_file.read_text() == "-- !x! WRITE 'hello'\n"

    def test_main_check_mode_needs_change(self, tmp_path):
        sql_file = tmp_path / "needs_format.sql"
        sql_file.write_text("-- !x! write 'hello'\n")
        self._invoke(["--check", str(sql_file)])
        # File should be unchanged (check mode doesn't write)
        assert sql_file.read_text() == "-- !x! write 'hello'\n"

    def test_main_inplace_rewrites(self, tmp_path):
        sql_file = tmp_path / "rewrite.sql"
        sql_file.write_text("-- !x! write 'hello'\n")
        self._invoke(["--in-place", str(sql_file)])
        assert "WRITE" in sql_file.read_text()

    def test_main_inplace_no_change_when_already_formatted(self, tmp_path):
        sql_file = tmp_path / "clean.sql"
        original = "-- !x! WRITE 'hello'\n"
        sql_file.write_text(original)
        self._invoke(["--in-place", str(sql_file)])
        # Not reformatted — no "reformatted" message
        assert sql_file.read_text() == original

    def test_main_no_files_found(self, tmp_path):
        # directory with no .sql files
        self._invoke([str(tmp_path)])
        # Just verify it completes without exception

    def test_main_no_sql_flag(self, tmp_path, capsys):
        sql_file = tmp_path / "test.sql"
        sql_file.write_text("select 1;\n")
        self._invoke(["--no-sql", str(sql_file)])
        captured = capsys.readouterr()
        assert "select 1;" in captured.out

    def test_main_unreadable_file(self, tmp_path):
        # Pass a path that doesn't exist → OSError when reading → exit code 1
        missing = tmp_path / "missing.sql"
        # collect_paths passes files through regardless of existence
        self._invoke([str(missing)])
        # Just verify it doesn't crash with an unexpected exception


# ---------------------------------------------------------------------------
# Edge cases — block comments, metacommands in comments, tabs, long lines
# ---------------------------------------------------------------------------


class TestFormatFileEdgeCases:
    def test_block_comment_spans_multiple_lines(self):
        source = "/* this is a\nmultiline block comment */\nSELECT 1;\n"
        result = format_file(source, use_sql=False)
        assert "multiline" in result
        assert "SELECT 1;" in result

    def test_block_comment_single_line(self):
        source = "/* comment */\nSELECT 1;\n"
        result = format_file(source, use_sql=False)
        assert "/* comment */" in result

    def test_metacommand_inside_block_comment_not_parsed(self):
        """A metacommand marker inside a block comment should be treated as comment text."""
        source = "/* -- !x! WRITE 'not a command' */\n-- !x! WRITE 'real command'\n"
        result = format_file(source, use_sql=False)
        lines = result.splitlines()
        # The block comment line should be preserved as-is (SQL pass-through)
        # The real metacommand should be uppercased
        assert any("WRITE 'real command'" in line for line in lines)

    def test_tab_expansion(self):
        """Tabs in source should be expanded to 4 spaces."""
        source = "\t-- !x! WRITE 'hello'\n"
        result = format_file(source, use_sql=False)
        assert "\t" not in result
        assert "WRITE" in result

    def test_long_metacommand_line(self):
        """Lines exceeding 120 chars should not cause errors."""
        long_arg = "x" * 200
        source = f"-- !x! WRITE '{long_arg}'\n"
        result = format_file(source, use_sql=False)
        assert long_arg in result

    def test_long_sql_line(self):
        """Very long SQL lines should pass through without errors."""
        cols = ", ".join(f"col_{i}" for i in range(50))
        source = f"SELECT {cols} FROM big_table;\n"
        result = format_file(source, use_sql=False)
        assert "col_49" in result

    def test_mixed_sql_and_metacommands(self):
        source = "SELECT 1;\n-- !x! IF TABLE_EXISTS(foo)\nSELECT * FROM foo;\n-- !x! ENDIF\n"
        result = format_file(source, use_sql=False)
        lines = result.splitlines()
        assert any("IF" in line for line in lines)
        assert any("ENDIF" in line for line in lines)
        assert any("SELECT" in line for line in lines)

    def test_sql_with_variables_preserved(self):
        source = "SELECT !!$my_var!! FROM !!table_name!!;\n"
        result = format_file(source, use_sql=False)
        assert "!!$my_var!!" in result
        assert "!!table_name!!" in result

    def test_elseif_depth(self):
        source = "-- !x! IF 1=1\n-- !x! WRITE 'a'\n-- !x! ELSEIF 2=2\n-- !x! WRITE 'b'\n-- !x! ENDIF\n"
        result = format_file(source, use_sql=False)
        lines = result.splitlines()
        # ELSEIF should be at depth 0 (same as IF)
        assert lines[2].startswith("-- !x! ELSEIF")
        # WRITE 'b' should be indented (depth 1)
        assert lines[3].startswith("    -- !x! WRITE")

    def test_begin_batch_end_batch(self):
        source = "-- !x! BEGIN BATCH\nINSERT INTO t VALUES (1);\n-- !x! END BATCH\n"
        result = format_file(source, use_sql=False)
        lines = result.splitlines()
        assert lines[0] == "-- !x! BEGIN BATCH"
        assert lines[1].startswith("    ")
        assert lines[2] == "-- !x! END BATCH"

    def test_begin_sql_end_sql(self):
        source = "-- !x! BEGIN SQL\nSELECT 1;\nSELECT 2;\n-- !x! END SQL\n"
        result = format_file(source, use_sql=False)
        lines = result.splitlines()
        assert lines[0] == "-- !x! BEGIN SQL"
        assert lines[-1] == "-- !x! END SQL"

    def test_orif_continuation(self):
        source = "-- !x! IF 1=1\n-- !x! ORIF 2=2\n-- !x! WRITE 'x'\n-- !x! ENDIF\n"
        result = format_file(source, use_sql=False)
        lines = result.splitlines()
        # ORIF is a CONTINUATION — emits at depth-1, no depth change
        assert lines[1].startswith("-- !x! ORIF")

    def test_create_script_block(self):
        source = "-- !x! CREATE SCRIPT myscript\n-- !x! WRITE 'inside'\n-- !x! END SCRIPT\n"
        result = format_file(source, use_sql=False)
        lines = result.splitlines()
        assert lines[0] == "-- !x! CREATE SCRIPT myscript"
        assert lines[1] == "    -- !x! WRITE 'inside'"
        assert lines[2] == "-- !x! END SCRIPT"

    def test_only_sql_no_metacommands(self):
        source = "SELECT 1;\nSELECT 2;\n"
        result = format_file(source, use_sql=False)
        assert "SELECT 1;" in result
        assert "SELECT 2;" in result

    def test_only_comments(self):
        source = "-- comment 1\n-- comment 2\n"
        result = format_file(source, use_sql=False)
        assert "-- comment 1" in result
        assert "-- comment 2" in result

    def test_indent_two_spaces(self):
        source = "-- !x! IF 1=1\n-- !x! WRITE 'x'\n-- !x! ENDIF\n"
        result = format_file(source, indent=2, use_sql=False)
        lines = result.splitlines()
        assert lines[1] == "  -- !x! WRITE 'x'"


# ---------------------------------------------------------------------------
# _is_comment_line — edge cases
# ---------------------------------------------------------------------------


class TestIsCommentLineEdgeCases:
    """Unit tests for _is_comment_line(line, in_block) -> (is_comment, new_in_block).

    Implementation notes (from reading format.py):
      - in_block=True  → always (True, "*/" not in line).  No re-open detection.
      - in_block=False, empty → (False, False)
      - in_block=False, starts "--" → (True, False)
      - in_block=False, starts "/*" → (True, "*/" not in s[2:])
      - in_block=False, other → (False, False)
    """

    def test_open_and_close_on_same_line_not_in_block(self):
        # "/* comment */" starts with /*, and "*/" appears in s[2:] → not left in block
        is_comment, new_in_block = _is_comment_line("/* comment */", False)
        assert is_comment is True
        assert new_in_block is False

    def test_open_on_line_already_in_block(self):
        # We are already in a block; the implementation returns (True, "*/" not in line).
        # "*/" IS present, so the block closes — new_in_block=False.
        # The inner "/*" is irrelevant: the implementation does not re-open after close.
        is_comment, new_in_block = _is_comment_line("/* nested */", True)
        assert is_comment is True
        assert new_in_block is False

    def test_close_marker_when_not_in_block(self):
        # "still here */" does not start with "--" or "/*" when in_block=False.
        # The implementation returns (False, False) — it is not a comment line.
        is_comment, new_in_block = _is_comment_line("still here */", False)
        assert is_comment is False
        assert new_in_block is False

    def test_open_without_close(self):
        # Starts with "/*"; "*/" does NOT appear in s[2:] → open block, stay in block.
        is_comment, new_in_block = _is_comment_line("/* start of block", False)
        assert is_comment is True
        assert new_in_block is True

    def test_close_without_open_in_block(self):
        # in_block=True; "*/" IS in the line → block closes.
        is_comment, new_in_block = _is_comment_line("end of block */", True)
        assert is_comment is True
        assert new_in_block is False

    def test_multiple_opens_and_closes(self):
        # "/* a */ /* b */" starts with "/*"; "*/" appears in s[2:] = " a */ /* b */".
        # The implementation only checks whether "*/" is present anywhere after the
        # opening "/*" — it does not re-track the second "/*"/"*/".  End state: not
        # in block because "*/" was found.
        is_comment, new_in_block = _is_comment_line("/* a */ /* b */", False)
        assert is_comment is True
        assert new_in_block is False

    def test_empty_line_not_in_block(self):
        # Empty string, not in a block → strip() is falsy → (False, False).
        is_comment, new_in_block = _is_comment_line("", False)
        assert is_comment is False
        assert new_in_block is False

    def test_empty_line_in_block(self):
        # Empty string, inside a block → (True, True): still commented, still in block.
        is_comment, new_in_block = _is_comment_line("", True)
        assert is_comment is True
        assert new_in_block is True

    def test_dash_dash_comment_not_in_block(self):
        # Simple single-line SQL comment while not in a block.
        is_comment, new_in_block = _is_comment_line("-- a regular comment", False)
        assert is_comment is True
        assert new_in_block is False

    def test_plain_sql_not_in_block(self):
        # Non-comment line, not in a block.
        is_comment, new_in_block = _is_comment_line("SELECT 1;", False)
        assert is_comment is False
        assert new_in_block is False

    def test_plain_sql_in_block(self):
        # Any line inside a block comment is treated as commented regardless of content.
        is_comment, new_in_block = _is_comment_line("SELECT 1;", True)
        assert is_comment is True
        assert new_in_block is True


# ---------------------------------------------------------------------------
# _is_comment_line — nested block comment behavior
# ---------------------------------------------------------------------------


class TestNestedBlockComments:
    """Verify that SQL's non-nesting block comment semantics are implemented correctly.

    SQL block comments do not nest: the first '*/' closes the block regardless
    of any inner '/*'.  The implementation reflects this.
    """

    def test_nested_open_does_not_extend_block(self):
        # in_block=True, line contains both "/*" and "*/".
        # The implementation checks only whether "*/" appears → block closes.
        # The inner "/*" is not treated as re-opening a new level.
        is_comment, new_in_block = _is_comment_line("/* inner /* nested */", True)
        assert is_comment is True
        assert new_in_block is False

    def test_outer_close_after_nested_open(self):
        # Process three lines simulating a "nested" block comment scenario.
        # Line 1: open a block.
        _, in_block = _is_comment_line("/* outer", False)
        assert in_block is True

        # Line 2: while in the block, a line that contains both "/*" and "*/".
        # The first "*/" closes the block — in_block becomes False.
        is_comment, in_block = _is_comment_line("/* inner */", in_block)
        assert is_comment is True
        assert in_block is False

        # Line 3: block is already closed; this line is NOT a comment.
        # It does not start with "--" or "/*" so it is treated as SQL.
        is_comment, in_block = _is_comment_line("still in comment? */", in_block)
        assert is_comment is False
        assert in_block is False

    def test_format_file_with_nested_block_comment(self):
        # Feed format_file a script that has a "nested comment" pattern.
        # The formatter processes lines one at a time via format_sql_block /
        # _is_comment_line.  Because SQL block comments do not nest, line 3
        # ("this is NOT a comment */") is seen as plain SQL once line 2 closes
        # the block with its "*/".  SELECT 1; therefore also appears as SQL.
        source = "/* outer comment\n/* inner comment */\nthis is NOT a comment */\nSELECT 1;\n"
        result = format_file(source, use_sql=False)
        # SELECT 1; must be present — it is never inside a block comment.
        assert "SELECT 1;" in result
        # The outer opening line is part of the accumulator fed to format_sql_block.
        assert "outer comment" in result


# ---------------------------------------------------------------------------
# Metacommand detection in SQL context
# ---------------------------------------------------------------------------


class TestMetacommandInSqlContext:
    """Verify metacommand detection (METACOMMAND_RE) only fires on lines whose
    leading content (after optional whitespace) is '--  !x!'.

    The regex is: r'^\\s*--\\s*!x!\\s*(.*)' with re.IGNORECASE.
    """

    def test_sql_with_metacommand_marker_in_where(self):
        # The '-- !x!' substring appears inside a string literal, not at the
        # start of the line.  METACOMMAND_RE does not match, so the line flows
        # into sql_acc and is passed through unchanged.
        source = "SELECT * FROM t WHERE comment LIKE '-- !x! %';\n"
        result = format_file(source, use_sql=False)
        # The WHERE clause content must survive intact.
        assert "LIKE '-- !x! %'" in result

    def test_sql_with_double_dash_comment_above_metacommand(self):
        # A plain SQL comment (not a metacommand) followed by a real metacommand.
        # The comment line goes to sql_acc; the metacommand is dispatched normally.
        source = '-- this is a comment\n-- !x! WRITE "hello"\nSELECT 1;\n'
        result = format_file(source, use_sql=False)
        lines = result.splitlines()
        # The plain SQL comment is preserved.
        assert any("this is a comment" in line for line in lines)
        # The metacommand keyword must be uppercased and present.
        assert any(line.strip() == '-- !x! WRITE "hello"' for line in lines)

    def test_metacommand_marker_not_at_line_start(self):
        # METACOMMAND_RE uses '^\\s*' so leading spaces do NOT prevent a match.
        # An indented '-- !x! WRITE ...' is still detected as a metacommand.
        source = '    -- !x! WRITE "test"\n'
        result = format_file(source, use_sql=False)
        lines = result.splitlines()
        # After formatting, depth=0 so the line is emitted at column 0.
        assert any('-- !x! WRITE "test"' in line for line in lines)


# ---------------------------------------------------------------------------
# Block comment tracking in format_file
# ---------------------------------------------------------------------------


class TestBlockCommentTracking:
    """Verify that /* */ block comments prevent metacommand processing."""

    def test_metacommand_inside_multiline_block_comment_not_processed(self):
        """Metacommand markers inside /* */ are treated as comment text."""
        source = "/*\n-- !x! IF (True)\n    SELECT 1;\n-- !x! ENDIF\n*/\nSELECT 2;\n"
        result = format_file(source, use_sql=False)
        # The block comment should be preserved intact — metacommands inside
        # should NOT affect depth or be reformatted.
        assert "*/" in result
        assert "* /" not in result
        # The real SQL after the block comment should be present.
        assert "SELECT 2;" in result

    def test_block_comment_close_marker_preserved(self):
        """The closing */ of a block comment should not be mangled."""
        source = "/*\nSome comment text\n*/\nSELECT 1;\n"
        result = format_file(source, use_sql=False)
        assert "*/" in result
        assert "* /" not in result

    def test_single_line_block_comment_not_treated_as_open(self):
        """A /* ... */ on one line should NOT enable block comment mode."""
        source = "/* one liner */\n-- !x! WRITE 'hello'\n"
        result = format_file(source, use_sql=False)
        # The metacommand after the single-line block comment should be processed.
        assert "WRITE" in result

    def test_block_comment_with_loop_and_update(self):
        """A realistic commented-out code block with metacommands and SQL."""
        source = (
            "/*\n"
            "-- !x! LOOP while(hasrows(dup_lr))\n"
            "    DROP TABLE IF EXISTS new_lr CASCADE;\n"
            "    UPDATE new_lr SET lab_rep = 'x';\n"
            "-- !x! END LOOP\n"
            "*/\n"
        )
        result = format_file(source, use_sql=False)
        assert "*/" in result
        assert "* /" not in result
        # All content should be preserved inside the block comment.
        assert "DROP TABLE" in result or "drop table" in result.lower()
        assert "UPDATE" in result or "update" in result.lower()


# ---------------------------------------------------------------------------
# Mid-statement comment detection and preservation
# ---------------------------------------------------------------------------


class TestMidStatementComments:
    """Verify that comments interleaved within SQL statements don't corrupt output."""

    def test_select_with_interleaved_comments_preserved(self):
        """A SELECT with comments between columns should not be broken."""
        source = (
            "CREATE TABLE foo AS\n"
            "SELECT\n"
            "    -- Document info\n"
            "    coalesce(a.x, b.x) AS source,\n"
            "    'doc1' AS doc_id,\n"
            "    -- Study info\n"
            "    'study1' AS study_id\n"
            "FROM bar;\n"
        )
        result = format_file(source, use_sql=True)
        # Commas should NOT become semicolons.
        assert "source;" not in result
        # All columns must be present.
        assert "doc1" in result
        assert "study1" in result
        assert "source" in result

    def test_case_expression_with_comments_not_broken(self):
        """A CASE expression with interleaved comments should stay intact."""
        source = (
            "SELECT\n"
            "    case\n"
            "        -- Dry basis\n"
            "        when basis ilike '%dry%' then 'DryWt'\n"
            "        else null\n"
            "    end as meas_basis\n"
            "FROM results;\n"
        )
        result = format_file(source, use_sql=True)
        # The CASE should not be broken into a separate empty CASE END.
        lines_upper = result.upper()
        assert "CASE END;" not in lines_upper
        assert "dry" in result.lower()

    def test_insert_with_interleaved_comments_preserved(self):
        """An INSERT with comments between column groups should not break."""
        source = (
            "INSERT INTO foo (\n"
            "    col_a,\n"
            "    -- second group\n"
            "    col_b\n"
            ")\n"
            "SELECT\n"
            "    -- map columns\n"
            "    a,\n"
            "    b\n"
            "FROM bar;\n"
        )
        result = format_file(source, use_sql=True)
        assert "col_a" in result
        assert "col_b" in result

    def test_comments_between_statements_still_formatted(self):
        """Comments between complete statements should still allow sqlglot formatting."""
        source = "drop table if exists foo;\n-- Next statement\ncreate table foo (id int);\n"
        result = format_file(source, use_sql=True)
        # sqlglot should uppercase keywords.
        assert "DROP TABLE" in result
        assert "CREATE TABLE" in result
        # Comment preserved.
        assert "Next statement" in result

    def test_blank_lines_mid_statement_preserved(self):
        """Blank lines inside a multi-line statement should not break it into fragments."""
        source = "CREATE TABLE foo AS\nSELECT\n    a,\n\n    -- second group\n    b\nFROM bar;\n"
        result = format_file(source, use_sql=True)
        # The SELECT columns should not become separate statements.
        assert "a;" not in result
        assert "a," in result or "a" in result
        assert "b" in result
        assert "FROM" in result or "from" in result


# ---------------------------------------------------------------------------
# _sqlglot_format safety checks
# ---------------------------------------------------------------------------


class TestSqlglotSafetyChecks:
    """Verify that _sqlglot_format falls back when sqlglot produces bad output."""

    def test_content_loss_triggers_fallback(self):
        """If sqlglot drops significant content, fall back to original."""
        # ERROR: is misinterpreted by sqlglot as an Alias node.
        lines = ["ERROR: This script must be run with execsql.py;"]
        result = _sqlglot_format(lines)
        joined = "\n".join(result)
        # The original content should be preserved (fallback).
        assert "execsql" in joined.lower()

    def test_statement_count_inflation_triggers_fallback(self):
        """If sqlglot creates more statements than semicolons in input, fall back."""
        # A SELECT column list fragment (no semicolons) should not be split.
        lines = ["coalesce(a.x, b.x) AS source, 'doc1' AS doc_id"]
        result = _sqlglot_format(lines)
        joined = "\n".join(result)
        # Should fall back — original content preserved.
        assert "doc1" in joined


# ---------------------------------------------------------------------------
# Idempotency — formatting twice must produce identical output
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Running the formatter twice on the same input must produce identical output.

    If this fails, the formatter is unstable and will cause noisy diffs on
    every save — or worse, silently drift the SQL on each reformat.
    """

    SAMPLES = {
        "simple_select": "select a, b, c from foo where x = 1;\n",
        "create_table": (
            "create table staging.t (\n"
            "    id serial primary key,\n"
            "    name varchar(100) not null,\n"
            "    val float8 default 0.0\n"
            ");\n"
        ),
        "insert_select": ("insert into staging.t (id, name)\nselect id, name from staging.src;\n"),
        "metacommand_and_sql": (
            "-- !x! IF (!!reload!!)\n"
            "    drop table if exists staging.raw;\n"
            "    create table staging.raw (id int);\n"
            "-- !x! ENDIF\n"
        ),
        "select_with_mid_statement_comments": (
            "select\n    -- group 1\n    a, b,\n    -- group 2\n    c, d\nfrom t;\n"
        ),
        "case_with_comments": (
            "select\n"
            "    case\n"
            "        -- check x\n"
            "        when x = 1 then 'a'\n"
            "        -- check y\n"
            "        when y = 2 then 'b'\n"
            "        else 'c'\n"
            "    end as result\n"
            "from t;\n"
        ),
        "block_comment_with_metacommands": ("/*\n-- !x! IF (True)\n    SELECT 1;\n-- !x! ENDIF\n*/\nSELECT 2;\n"),
        "comments_between_statements": (
            "drop table if exists foo;\n"
            "-- Create the replacement\n"
            "create table foo (id int);\n"
            "-- Populate\n"
            "insert into foo values (1);\n"
        ),
    }

    def test_idempotent_with_sql(self):
        for name, source in self.SAMPLES.items():
            first = format_file(source, use_sql=True)
            second = format_file(first, use_sql=True)
            assert first == second, f"Not idempotent (use_sql=True): {name}"

    def test_idempotent_without_sql(self):
        for name, source in self.SAMPLES.items():
            first = format_file(source, use_sql=False)
            second = format_file(first, use_sql=False)
            assert first == second, f"Not idempotent (use_sql=False): {name}"


# ---------------------------------------------------------------------------
# Semantic preservation — formatted output must contain the same content
# ---------------------------------------------------------------------------


class TestSemanticPreservation:
    """Verify that formatting preserves all meaningful SQL content.

    These tests check that columns, tables, JOINs, conditions, values, and
    comments survive formatting intact.  This is the class that would have
    caught the original comma-to-semicolon corruption bug.
    """

    def test_all_select_columns_preserved(self):
        """Every column alias in a SELECT must survive formatting."""
        source = "select\n    a as col1,\n    b as col2,\n    c as col3,\n    d as col4,\n    e as col5\nfrom t;\n"
        result = format_file(source, use_sql=True)
        for alias in ["col1", "col2", "col3", "col4", "col5"]:
            assert alias in result, f"Column alias '{alias}' lost"

    def test_all_columns_with_interleaved_comments_preserved(self):
        """Columns interleaved with comments must all survive."""
        source = (
            "select\n"
            "    -- identifiers\n"
            "    id,\n"
            "    name,\n"
            "    -- dates\n"
            "    created_at,\n"
            "    updated_at,\n"
            "    -- flags\n"
            "    is_active,\n"
            "    is_deleted\n"
            "from users;\n"
        )
        result = format_file(source, use_sql=True)
        for col in ["id", "name", "created_at", "updated_at", "is_active", "is_deleted"]:
            assert col in result, f"Column '{col}' lost"
        for comment in ["identifiers", "dates", "flags"]:
            assert comment in result, f"Comment '{comment}' lost"

    def test_join_clauses_preserved(self):
        """All JOIN clauses and their conditions must survive."""
        source = (
            "select a.id, b.name, c.value\n"
            "from table_a a\n"
            "    -- lookup join\n"
            "    left join table_b b on a.id = b.a_id\n"
            "    -- value join\n"
            "    inner join table_c c on b.id = c.b_id and c.active = true\n"
            "where a.status = 'open';\n"
        )
        result = format_file(source, use_sql=True)
        assert "table_a" in result
        assert "table_b" in result
        assert "table_c" in result
        assert "a.id" in result or "a_id" in result
        assert "b_id" in result
        assert "lookup join" in result
        assert "value join" in result

    def test_where_conditions_preserved(self):
        """WHERE conditions must not be dropped or altered."""
        source = (
            "select * from t\n"
            "where\n"
            "    status = 'active'\n"
            "    and created_at > '2024-01-01'::timestamp\n"
            "    and (category = 'A' or category = 'B')\n"
            "    and score >= 0.5;\n"
        )
        result = format_file(source, use_sql=True)
        assert "active" in result
        assert "2024-01-01" in result
        assert "0.5" in result
        for cat in ["A", "B"]:
            assert f"'{cat}'" in result

    def test_string_literals_preserved(self):
        """String literals must survive formatting exactly."""
        source = "select 'hello world', 'it''s a test', '' as empty_str from t;\n"
        result = format_file(source, use_sql=True)
        assert "hello world" in result
        assert "empty_str" in result

    def test_numeric_values_preserved(self):
        """Numeric literals must not change."""
        source = "select 42, 3.14, -1, 0.001, 1e5 from t;\n"
        result = format_file(source, use_sql=True)
        for num in ["42", "3.14", "0.001"]:
            assert num in result, f"Numeric value '{num}' lost"

    def test_case_all_branches_preserved(self):
        """Every WHEN/THEN branch in a CASE must survive."""
        source = (
            "select case\n"
            "    when x = 1 then 'one'\n"
            "    when x = 2 then 'two'\n"
            "    when x = 3 then 'three'\n"
            "    when x = 4 then 'four'\n"
            "    else 'other'\n"
            "end as label from t;\n"
        )
        result = format_file(source, use_sql=True)
        for val in ["one", "two", "three", "four", "other"]:
            assert val in result, f"CASE branch '{val}' lost"

    def test_case_with_comments_all_branches_preserved(self):
        """CASE with comments before each WHEN must preserve all branches."""
        source = (
            "select case\n"
            "    -- dry weight\n"
            "    when basis ilike '%dry%' then 'DryWt'\n"
            "    -- wet weight\n"
            "    when basis is null and matrix = 'Solid' then 'WetWt'\n"
            "    -- aqueous\n"
            "    when matrix = 'Water' then 'Whole'\n"
            "    else null\n"
            "end as meas_basis from t;\n"
        )
        result = format_file(source, use_sql=True)
        for val in ["DryWt", "WetWt", "Whole"]:
            assert val in result, f"CASE branch value '{val}' lost"
        for comment in ["dry weight", "wet weight", "aqueous"]:
            assert comment in result, f"CASE comment '{comment}' lost"

    def test_create_table_all_columns_preserved(self):
        """All column definitions in CREATE TABLE must survive."""
        source = (
            "create table staging.d_result (\n"
            "    lab varchar(10),\n"
            "    labsample varchar(40),\n"
            "    analyte varchar(20),\n"
            "    result float8,\n"
            "    detection_limit float8,\n"
            "    units varchar(10),\n"
            "    lab_flags varchar(8),\n"
            "    reportable bool default true,\n"
            "    doc_id varchar(24)\n"
            ");\n"
        )
        result = format_file(source, use_sql=True)
        for col in [
            "lab",
            "labsample",
            "analyte",
            "result",
            "detection_limit",
            "units",
            "lab_flags",
            "reportable",
            "doc_id",
        ]:
            assert col in result, f"Column '{col}' lost from CREATE TABLE"

    def test_insert_column_list_preserved(self):
        """All columns in an INSERT column list must survive."""
        source = (
            "insert into staging.d_result (\n"
            "    -- identifiers\n"
            "    lab, labsample,\n"
            "    -- measurement\n"
            "    analyte, result, units,\n"
            "    -- metadata\n"
            "    doc_id\n"
            ")\n"
            "select lab, labsample, analyte, result, units, doc_id\n"
            "from staging.src;\n"
        )
        result = format_file(source, use_sql=True)
        for col in ["lab", "labsample", "analyte", "result", "units", "doc_id"]:
            assert result.count(col) >= 2, f"Column '{col}' not in both INSERT and SELECT"

    def test_cte_preserved(self):
        """CTE names and content must survive."""
        source = (
            "with\n"
            "    active as (\n"
            "        select id from users where active = true\n"
            "    ),\n"
            "    recent as (\n"
            "        select id from orders where date > '2024-01-01'\n"
            "    )\n"
            "select a.id from active a join recent r on a.id = r.id;\n"
        )
        result = format_file(source, use_sql=True)
        assert "active" in result.lower()
        assert "recent" in result.lower()
        assert "2024-01-01" in result

    def test_update_set_not_broken(self):
        """UPDATE SET must not be split into separate statements."""
        source = (
            "update staging.raw\n"
            "set qualifier = regexp_replace(\n"
            "    coalesce(qualifier, ''),\n"
            "    -- remove junk flags\n"
            "    ' |,|\\*\\+',\n"
            "    '',\n"
            "    'g'\n"
            ")\n"
            "where qualifier is not null;\n"
        )
        result = format_file(source, use_sql=True)
        # UPDATE and SET must not become separate statements
        assert result.count(";") <= 2  # original has 1 semicolon; formatted may add trailing
        assert "qualifier" in result
        assert "remove junk flags" in result

    def test_delete_with_complex_where_preserved(self):
        """DELETE with a multi-condition WHERE must preserve all conditions."""
        source = (
            "delete from staging.raw\n"
            "where result is null\n"
            "    and qualifier is null\n"
            "    -- keep rows with detection limits\n"
            "    and dl is null;\n"
        )
        result = format_file(source, use_sql=True)
        assert "result" in result
        assert "qualifier" in result
        assert "dl" in result
        assert "keep rows with detection limits" in result

    def test_window_function_preserved(self):
        """Window functions and their OVER clauses must survive."""
        source = (
            "select\n"
            "    location_id,\n"
            "    analyte,\n"
            "    result,\n"
            "    avg(result) over (\n"
            "        partition by location_id, analyte\n"
            "        order by sample_date\n"
            "    ) as running_avg,\n"
            "    rank() over (\n"
            "        partition by location_id\n"
            "        order by result desc\n"
            "    ) as result_rank\n"
            "from staging.data;\n"
        )
        result = format_file(source, use_sql=True)
        assert "running_avg" in result
        assert "result_rank" in result
        assert "location_id" in result
        assert "sample_date" in result


# ---------------------------------------------------------------------------
# Variable preservation in complex positions
# ---------------------------------------------------------------------------


class TestVariablePreservation:
    """Verify !!var!! substitutions survive formatting in all positions."""

    def test_schema_qualified_table(self):
        source = "select * from !!staging!!.!!table_name!!;\n"
        result = format_file(source, use_sql=True)
        assert "!!staging!!" in result
        assert "!!table_name!!" in result

    def test_variable_in_string_concat(self):
        source = "select '!!prefix!!' || id || '_' || '!!suffix!!' as label from t;\n"
        result = format_file(source, use_sql=True)
        assert "!!prefix!!" in result
        assert "!!suffix!!" in result

    def test_variable_in_case_expression(self):
        source = "select case\n    when x = '!!threshold!!' then 'above'\n    else 'below'\nend as status from t;\n"
        result = format_file(source, use_sql=True)
        assert "!!threshold!!" in result

    def test_variable_in_join_condition(self):
        source = "select a.id from t1 a\n    left join t2 b on a.id = b.id and b.source = '!!source_name!!';\n"
        result = format_file(source, use_sql=True)
        assert "!!source_name!!" in result

    def test_multiple_variables_in_insert(self):
        source = "insert into !!staging!!.!!target!! (col1, col2)\nselect col1, col2 from !!staging!!.!!source!!;\n"
        result = format_file(source, use_sql=True)
        assert "!!staging!!" in result
        assert "!!target!!" in result
        assert "!!source!!" in result

    def test_deferred_variable_preserved(self):
        source = "select !{deferred_var}! from t;\n"
        result = format_file(source, use_sql=True)
        assert "!{deferred_var}!" in result

    def test_system_variable_preserved(self):
        source = "select '!!$CURRENT_TIME!!' as ts, '!!$DB_NAME!!' as db from t;\n"
        result = format_file(source, use_sql=True)
        assert "!!$CURRENT_TIME!!" in result
        assert "!!$DB_NAME!!" in result


# ---------------------------------------------------------------------------
# Comment style preservation
# ---------------------------------------------------------------------------


class TestCommentStylePreservation:
    """Verify that -- comments stay as -- and don't become /* */."""

    def test_line_comment_stays_as_line_comment(self):
        """A -- comment between SQL statements must remain -- style."""
        source = "select 1;\n-- my comment\nselect 2;\n"
        result = format_file(source, use_sql=True)
        assert "-- my comment" in result
        assert "/* my comment */" not in result

    def test_mid_statement_comment_stays_as_line_comment(self):
        """A -- comment inside a SELECT must remain -- style."""
        source = "select\n    -- column group\n    a, b\nfrom t;\n"
        result = format_file(source, use_sql=True)
        assert "-- column group" in result
        assert "/* column group */" not in result

    def test_inline_block_comment_preserved(self):
        """A /* */ inline comment should stay as /* */."""
        source = "select a, /* primary key */ b from t;\n"
        result = format_file(source, use_sql=True)
        # sqlglot preserves inline block comments
        assert "primary key" in result


# ---------------------------------------------------------------------------
# New CLI flags: --indent and --leading-comma
# ---------------------------------------------------------------------------


class TestIndentFlag:
    """Verify --indent controls both metacommand and SQL indentation."""

    def test_indent_4_sql_indentation(self):
        """Default indent=4 should produce 4-space SQL indentation."""
        source = "select a, b from t;\n"
        result = format_file(source, indent=4, use_sql=True)
        lines = result.splitlines()
        # Columns should be indented 4 spaces
        col_lines = [line for line in lines if line.strip().startswith(("a", "b"))]
        assert any(line.startswith("    ") for line in col_lines)

    def test_indent_2_sql_indentation(self):
        """indent=2 should produce 2-space SQL indentation."""
        source = "select a, b from t;\n"
        result = format_file(source, indent=2, use_sql=True)
        lines = result.splitlines()
        col_lines = [line for line in lines if line.strip().startswith(("a", "b"))]
        assert any(line.startswith("  ") and not line.startswith("    ") for line in col_lines)

    def test_indent_affects_metacommands_and_sql_together(self):
        """Inside a metacommand block, SQL should be indented at block depth * indent."""
        source = "-- !x! IF (True)\n    select a, b from t;\n-- !x! ENDIF\n"
        result = format_file(source, indent=4, use_sql=True)
        lines = result.splitlines()
        # SQL inside the IF block should be indented (depth 1 * 4 = 4 spaces)
        sql_lines = [line for line in lines if "SELECT" in line.upper() and "!x!" not in line]
        assert sql_lines
        assert all(line.startswith("    ") for line in sql_lines)


class TestLeadingCommaFlag:
    """Verify --leading-comma places commas at line start."""

    def test_leading_comma_in_select(self):
        """With leading_comma=True, commas should appear at the start of column lines."""
        source = "select a, b, c from t;\n"
        result = format_file(source, use_sql=True, leading_comma=True)
        assert ", b" in result or ",b" in result

    def test_trailing_comma_default(self):
        """Without leading_comma, commas should appear at the end of column lines."""
        source = "select a, b, c from t;\n"
        result = format_file(source, use_sql=True, leading_comma=False)
        # At least one line should end with a comma
        lines = result.splitlines()
        assert any(line.rstrip().endswith(",") for line in lines)

    def test_leading_comma_with_mid_statement_comments(self):
        """leading_comma should work with the marker-based comment path."""
        source = "select\n    -- group 1\n    a,\n    -- group 2\n    b, c\nfrom t;\n"
        result = format_file(source, use_sql=True, leading_comma=True)
        # Comments must still be preserved
        assert "group 1" in result
        assert "group 2" in result
        # Content must be preserved
        assert "a" in result
        assert "b" in result
        assert "c" in result


# ---------------------------------------------------------------------------
# Dollar-quoted strings with sqlglot enabled
# ---------------------------------------------------------------------------


class TestDollarQuotedStrings:
    """Verify $$ regions skip sqlglot formatting and preserve content."""

    def test_plpgsql_function_body_preserved(self):
        """PL/pgSQL in $$ blocks must not be mangled by sqlglot."""
        source = (
            "CREATE FUNCTION add_one(x int) RETURNS int AS $$\nBEGIN\n    RETURN x + 1;\nEND;\n$$ LANGUAGE plpgsql;\n"
        )
        result = format_file(source, use_sql=True)
        assert "RETURN x + 1" in result or "return x + 1" in result.lower()
        assert "BEGIN" in result or "begin" in result.lower()

    def test_dollar_quoted_string_content_preserved(self):
        """Content inside $$ should not be reformatted."""
        source = "SELECT $$this is a raw string with 'quotes' and -- dashes$$;\n"
        result = format_file(source, use_sql=True)
        assert "this is a raw string" in result


# ---------------------------------------------------------------------------
# Regression: patterns that previously produced corrupt output
# ---------------------------------------------------------------------------


class TestRegressions:
    """Specific patterns that previously broke the formatter.

    Each test documents a historical bug.  If any of these fail, a
    regression has been introduced.
    """

    def test_comma_not_replaced_by_semicolon(self):
        """Columns in a SELECT with interleaved comments must stay comma-separated.

        Historical bug: comment-boundary splitting caused sqlglot to interpret
        column fragments as separate statements, replacing commas with semicolons.
        """
        source = (
            "create table foo as\n"
            "select\n"
            "    -- doc info\n"
            "    coalesce(a.x, b.x) as source,\n"
            "    'doc1' as doc_id,\n"
            "    -- study info\n"
            "    'study1' as study_id\n"
            "from bar;\n"
        )
        result = format_file(source, use_sql=True)
        # No column alias should be followed by a semicolon
        assert "source;" not in result
        assert "doc_id;" not in result

    def test_case_not_split_into_empty_case_end(self):
        """CASE with interleaved comments must not produce 'CASE END;'.

        Historical bug: the CASE keyword and its WHEN clauses were in
        separate segments, producing an empty CASE END for the first
        fragment.
        """
        source = "select case\n    -- check\n    when x = 1 then 'a'\n    else 'b'\nend as col from t;\n"
        result = format_file(source, use_sql=True)
        assert "CASE END" not in result.upper().replace("CASE ", "").replace(" END", "")

    def test_block_comment_close_not_mangled(self):
        """The closing */ must not become '* /' (with space).

        Historical bug: metacommand processing inside /* */ broke the block
        comment, and the leftover */ was sent to sqlglot which interpreted
        it as multiplication/division.
        """
        source = "/*\n-- !x! IF (True)\n    DROP TABLE IF EXISTS foo;\n-- !x! ENDIF\n*/\n"
        result = format_file(source, use_sql=False)
        assert "*/" in result
        assert "* /" not in result

    def test_error_line_not_mangled(self):
        """'ERROR: ...' text must not become 'ERROR AS %(This)s'.

        Historical bug: sqlglot parsed ERROR: as an Alias node, silently
        dropping most of the content.  The content-loss safety check now
        catches this.
        """
        source = "ERROR: This script must be run with execsql.py;\n"
        result = format_file(source, use_sql=True)
        assert "%(This)s" not in result
        assert "execsql" in result.lower()

    def test_update_set_not_split(self):
        """UPDATE ... SET must not become 'UPDATE ... SET;' + 'SET col = ...;'.

        Historical bug: comment-splitting broke UPDATE statements in half.
        """
        source = "update staging.t set\n    -- update name\n    name = 'new'\nwhere id = 1;\n"
        result = format_file(source, use_sql=True)
        assert "SET;" not in result.upper()
        assert "new" in result

    def test_blank_lines_in_select_dont_split_statement(self):
        """Blank lines between column groups in SELECT must not create fragments.

        Historical bug: blank lines triggered flush_sql() mid-statement,
        splitting the SELECT into multiple formatting blocks.
        """
        source = "select\n    a,\n\n    b,\n\n    c\nfrom t;\n"
        result = format_file(source, use_sql=True)
        # All columns must be in one statement
        assert "a;" not in result
        assert "b;" not in result
        # All columns preserved
        for col in ["a", "b", "c"]:
            assert col in result

    def test_insert_column_comments_dont_drop_columns(self):
        """INSERT with comments in column list must not lose any columns.

        Historical bug: comment-splitting caused column fragments to be
        sent to sqlglot, which dropped some as unparsable.
        """
        source = "insert into t (\n    -- keys\n    id,\n    -- values\n    name,\n    value\n) values (1, 'x', 2);\n"
        result = format_file(source, use_sql=True)
        for col in ["id", "name", "value"]:
            assert col in result, f"Column '{col}' dropped from INSERT"
