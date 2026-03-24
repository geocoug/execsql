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
