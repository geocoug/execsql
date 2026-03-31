"""End-to-end CLI tests — invoke the real CLI via subprocess and verify behavior."""

from __future__ import annotations

import json
import subprocess
import sys


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_execsql(*args: str, **kwargs) -> subprocess.CompletedProcess[str]:
    """Invoke ``python -m execsql`` with the given arguments."""
    return subprocess.run(
        [sys.executable, "-m", "execsql", *args],
        capture_output=True,
        text=True,
        **kwargs,
    )


def _run_formatter(*args: str) -> subprocess.CompletedProcess[str]:
    """Invoke the execsql-format entry point via Python."""
    return subprocess.run(
        [sys.executable, "-c", "from execsql.format import main; main()", *args],
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# --version
# ---------------------------------------------------------------------------


def test_version_exits_zero():
    result = _run_execsql("--version")
    assert result.returncode == 0


def test_version_prints_semver():
    result = _run_execsql("--version")
    import re

    assert re.search(r"\d+\.\d+\.\d+", result.stdout), f"Version output does not contain semver: {result.stdout!r}"


# ---------------------------------------------------------------------------
# --help
# ---------------------------------------------------------------------------


def test_help_exits_zero():
    result = _run_execsql("--help")
    assert result.returncode == 0


def test_help_contains_usage():
    result = _run_execsql("--help")
    combined = (result.stdout or "") + (result.stderr or "")
    assert "Usage" in combined or "usage" in combined


# ---------------------------------------------------------------------------
# --dump-keywords
# ---------------------------------------------------------------------------


def test_dump_keywords_exits_zero():
    result = _run_execsql("--dump-keywords")
    assert result.returncode == 0, result.stderr


def test_dump_keywords_valid_json():
    result = _run_execsql("--dump-keywords")
    data = json.loads(result.stdout)
    for key in (
        "metacommands",
        "conditions",
        "config_options",
        "export_formats",
        "database_types",
        "variable_patterns",
    ):
        assert key in data, f"Missing key: {key}"


def test_dump_keywords_metacommand_categories_nonempty():
    result = _run_execsql("--dump-keywords")
    data = json.loads(result.stdout)
    mc = data["metacommands"]
    for cat in ("control", "block", "action", "config", "prompt"):
        assert len(mc.get(cat, [])) > 0, f"Empty category: {cat}"


# ---------------------------------------------------------------------------
# -c (inline command) with SQLite
# ---------------------------------------------------------------------------


def test_inline_command_exits_zero(tmp_path):
    db = tmp_path / "test.db"
    db.touch()
    result = _run_execsql("-c", '-- !x! write "hello world"', str(db), "-t", "l")
    assert result.returncode == 0, result.stderr


def test_inline_command_output(tmp_path):
    db = tmp_path / "test.db"
    db.touch()
    result = _run_execsql("-c", '-- !x! write "hello world"', str(db), "-t", "l")
    assert "hello world" in result.stdout


def test_inline_command_sub_and_write(tmp_path):
    db = tmp_path / "test.db"
    db.touch()
    script = '-- !x! sub myvar hello\n-- !x! write "!!myvar!!"'
    result = _run_execsql("-c", script, str(db), "-t", "l")
    assert result.returncode == 0, result.stderr
    assert "hello" in result.stdout


def test_inline_sql_create_and_query(tmp_path):
    """Run actual SQL statements against a fresh SQLite database."""
    db = tmp_path / "test.db"
    db.touch()
    script = "CREATE TABLE t (val INTEGER);\nINSERT INTO t VALUES (42);"
    result = _run_execsql("-c", script, str(db), "-t", "l")
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# Script file execution with SQLite
# ---------------------------------------------------------------------------


def test_script_file_exits_zero(tmp_path):
    db = tmp_path / "test.db"
    db.touch()
    script = tmp_path / "test.sql"
    script.write_text('-- !x! sub myvar hello\n-- !x! write "!!myvar!!"\n')
    result = _run_execsql(str(script), str(db), "-t", "l")
    assert result.returncode == 0, result.stderr


def test_script_file_output(tmp_path):
    db = tmp_path / "test.db"
    db.touch()
    script = tmp_path / "test.sql"
    script.write_text('-- !x! sub myvar hello\n-- !x! write "!!myvar!!"\n')
    result = _run_execsql(str(script), str(db), "-t", "l")
    assert "hello" in result.stdout


def test_script_file_sql_statements(tmp_path):
    """Execute SQL DDL/DML from a script file against SQLite."""
    db = tmp_path / "test.db"
    db.touch()
    script = tmp_path / "query.sql"
    script.write_text("CREATE TABLE t (val INTEGER);\nINSERT INTO t VALUES (42);\n")
    result = _run_execsql(str(script), str(db), "-t", "l")
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# --dry-run
# ---------------------------------------------------------------------------


def test_dry_run_exits_zero(tmp_path):
    script = tmp_path / "test.sql"
    script.write_text('-- !x! sub myvar hello\n-- !x! write "!!myvar!!"\n')
    result = _run_execsql("--dry-run", str(script))
    assert result.returncode == 0, result.stderr


def test_dry_run_shows_commands(tmp_path):
    script = tmp_path / "test.sql"
    script.write_text('-- !x! sub myvar hello\n-- !x! write "!!myvar!!"\n')
    result = _run_execsql("--dry-run", str(script))
    assert "2 command(s)" in result.stdout
    assert "METACMD" in result.stdout


def test_dry_run_does_not_connect_to_db(tmp_path):
    """Dry-run should not require a database — only parses the script."""
    script = tmp_path / "test.sql"
    script.write_text("CREATE TABLE t (id INTEGER);\n")
    result = _run_execsql("--dry-run", str(script))
    assert result.returncode == 0, result.stderr
    assert "1 command(s)" in result.stdout


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_no_script_file_exits_nonzero():
    """Running with no arguments at all should exit non-zero."""
    result = _run_execsql()
    assert result.returncode != 0


def test_no_script_file_error_message():
    result = _run_execsql()
    combined = result.stdout + result.stderr
    assert "No SQL script file specified" in combined or "Usage" in combined


def test_nonexistent_script_exits_nonzero(tmp_path):
    fake = str(tmp_path / "this_file_does_not_exist_12345.sql")
    result = _run_execsql(fake)
    assert result.returncode == 1


def test_nonexistent_script_error_message(tmp_path):
    fake = str(tmp_path / "this_file_does_not_exist_12345.sql")
    result = _run_execsql(fake)
    combined = (result.stdout or "") + (result.stderr or "")
    # Rich may wrap long paths across lines, so collapse whitespace before checking.
    collapsed = " ".join(combined.split())
    assert "does not exist" in collapsed


# ---------------------------------------------------------------------------
# execsql-format CLI
# ---------------------------------------------------------------------------


def test_formatter_help_exits_zero():
    result = _run_formatter("--help")
    assert result.returncode == 0


def test_formatter_help_contains_usage():
    result = _run_formatter("--help")
    combined = (result.stdout or "") + (result.stderr or "")
    assert "Usage" in combined or "usage" in combined


def test_formatter_check_mode(tmp_path):
    """Formatter --check on an already-formatted file exits 0."""
    script = tmp_path / "formatted.sql"
    script.write_text('-- !x! SUB myvar hello\n-- !x! WRITE "!!myvar!!"\n')
    result = _run_formatter("--check", str(script))
    assert result.returncode == 0, result.stderr


def test_formatter_stdout_output(tmp_path):
    """Formatter prints formatted output to stdout by default."""
    script = tmp_path / "test.sql"
    script.write_text("-- !x! sub myvar hello\n")
    result = _run_formatter(str(script))
    assert result.returncode == 0, result.stderr
    assert "SUB" in result.stdout  # keywords should be uppercased


def test_formatter_no_args_shows_usage():
    """Running with no arguments should show usage information."""
    result = _run_formatter()
    combined = (result.stdout or "") + (result.stderr or "")
    assert "Usage" in combined or "FILE_OR_DIR" in combined
