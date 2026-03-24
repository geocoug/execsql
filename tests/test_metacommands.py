"""Integration tests for execsql metacommands.

Tests use the full CLI pipeline (typer.testing.CliRunner → SQLite) to verify
that every major metacommand category still works after the GUI/filewriter
refactor.

Pattern
-------
- ``script_runner`` fixture: writes a .sql file, invokes the CLI against a
  fresh SQLite database, returns (result, db_path).
- ``qdb`` helper: queries the resulting SQLite DB for assertions.
- Variable-value assertions use SQL tables (``insert into t values ('!!v!!')``)
  rather than file writes, to avoid the async FileWriter race.
- File-existence / file-content assertions call ``_flush_filewriter()`` after
  the CLI run to ensure the FileWriter subprocess has processed all writes.
"""

from __future__ import annotations

import csv
import json
import sqlite3
import textwrap
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from execsql.cli import app
import execsql.state as _state
from execsql.exceptions import ErrInfo

_runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flush_filewriter() -> None:
    """Block until the FileWriter subprocess has flushed all pending writes.

    Uses a CMD_PING with a unique token so we can unambiguously identify our
    own response and discard any stale STATUS_CLOSED responses from earlier
    flush calls — eliminating the race condition where the drain removes our
    own response.
    """
    import queue as _queue
    import time

    try:
        if _state.filewriter is None or not _state.filewriter.is_alive():
            return
        # Allow any in-flight CMD_SHUTDOWN (queued by exit_now) to be processed
        # before we send more commands.  If the process exits cleanly within the
        # brief window, skip the ping entirely.
        _state.filewriter.join(timeout=0.3)
        if not _state.filewriter.is_alive():
            return
        from execsql.utils.fileio import fw_input, fw_output, FileWriter

        token = ("_flush", time.monotonic())
        # Close all open files (flushing queued content), then echo our token.
        fw_input.put((FileWriter.CMD_CLOSE_ALL_AFTER_WRITE, ()))
        fw_input.put((FileWriter.CMD_PING, (token,)))
        # Discard stale responses until we see ours (up to 5 s).
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                msg = fw_output.get(timeout=0.1)
                if msg == token:
                    return
            except _queue.Empty:
                pass
    except Exception:
        pass


def qdb(db_path: Path, sql: str) -> list[tuple[Any, ...]]:
    """Execute *sql* against the test SQLite database and return all rows."""
    with sqlite3.connect(db_path) as conn:
        return conn.execute(sql).fetchall()


def table_exists(db_path: Path, table: str) -> bool:
    rows = qdb(
        db_path,
        f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'",
    )
    return bool(rows)


# ---------------------------------------------------------------------------
# State reset
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_execsql_state():
    """Reset execsql global state between integration tests.

    The CLI initialises module-level singletons (subvars, if_stack, status,
    dbs, …) on each run; after the CLI returns those singletons remain set.
    The conftest ``minimal_conf`` fixture restores ``_state.conf`` but leaves
    all other globals untouched.  This fixture clears the ones most likely to
    cause cross-test pollution.
    """
    yield
    # After each test: clear anything the CLI might have dirtied.
    _state.commandliststack.clear()
    _state.loopcommandstack.clear()
    _state.compiling_loop = False
    _state.loop_nest_level = 0
    _state.cmds_run = 0
    _state.subvars = None
    _state.if_stack = None
    _state.counters = None
    _state.timer = None
    _state.output = None
    _state.dbs = None
    _state.tempfiles = None
    _state.export_metadata = None
    _state.status = None
    _state.exec_log = None
    _state.last_command = None
    _state.err_halt_writespec = None
    _state.err_halt_email = None
    _state.err_halt_exec = None
    _state.cancel_halt_writespec = None
    _state.cancel_halt_mailspec = None
    _state.cancel_halt_exec = None
    # GUI manager
    _state.gui_manager_queue = None
    _state.gui_manager_thread = None
    _state.gui_console = None
    # Reset the module-level active backend so the next test gets a fresh one
    import execsql.utils.gui as _gui_mod

    _gui_mod._active_backend = None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def script_runner(tmp_path: Path):
    """Return a callable that runs an execsql script against a SQLite DB.

    Usage::

        result, db_path = script_runner('''
            -- !x! sub myvar hello
        ''')

    Returns *(result, db_path)*.  After calling, the fixture waits for the
    FileWriter subprocess to flush all pending file writes.
    """
    db_path = tmp_path / "test.db"
    script_file = tmp_path / "test.sql"

    def run(
        script: str,
        *,
        gui_level: int = 0,
        new_db: bool = True,
        extra_args: list[str] | None = None,
        catch_exceptions: bool = False,
    ):
        script_file.write_text(textwrap.dedent(script).strip(), encoding="utf-8")
        args = [str(script_file), str(db_path), "-t", "l"]
        if new_db:
            args.append("-n")
        if gui_level:
            args += ["-v", str(gui_level)]
        if extra_args:
            args.extend(extra_args)
        result = _runner.invoke(app, args, catch_exceptions=catch_exceptions)
        _flush_filewriter()
        return result, db_path

    return run


# ---------------------------------------------------------------------------
# Substitution-variable metacommands
# ---------------------------------------------------------------------------


class TestSubstitutionVars:
    """SUB, SUB_ADD, SUB_APPEND, SUB_EMPTY, RM_SUB, SUB_TEMPFILE,
    SUB_LOCAL, SUB_QUERYSTRING, SUB_INI, SUBDATA, SELECT_SUB."""

    def test_sub_basic(self, script_runner):
        result, db = script_runner("""
            -- !x! sub greeting hello
            create table result (val text);
            insert into result values ('!!greeting!!');
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT val FROM result") == [("hello",)]

    def test_sub_numeric(self, script_runner):
        result, db = script_runner("""
            -- !x! sub num 42
            create table result (val text);
            insert into result values ('!!num!!');
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT val FROM result") == [("42",)]

    def test_sub_overwrite(self, script_runner):
        result, db = script_runner("""
            -- !x! sub val first
            -- !x! sub val second
            create table result (val text);
            insert into result values ('!!val!!');
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT val FROM result") == [("second",)]

    def test_sub_add(self, script_runner):
        result, db = script_runner("""
            -- !x! sub counter 10
            -- !x! sub_add counter 5
            create table result (val text);
            insert into result values ('!!counter!!');
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT val FROM result") == [("15",)]

    def test_sub_add_negative(self, script_runner):
        result, db = script_runner("""
            -- !x! sub counter 10
            -- !x! sub_add counter -3
            create table result (val text);
            insert into result values ('!!counter!!');
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT val FROM result") == [("7",)]

    def test_sub_append(self, script_runner):
        """SUB_APPEND concatenates with a newline separator by design."""
        result, db = script_runner("""
            -- !x! sub msg hello
            -- !x! sub_append msg world
            create table result (val text);
            insert into result values ('!!msg!!');
        """)
        assert result.exit_code == 0, result.output
        # SUB_APPEND joins with '\n' as separator
        rows = qdb(db, "SELECT val FROM result")
        assert rows[0][0] == "hello\nworld"

    def test_sub_empty(self, script_runner):
        result, db = script_runner("""
            -- !x! sub myvar filled
            -- !x! sub_empty myvar
            create table result (val text);
            insert into result values ('!!myvar!!');
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT val FROM result") == [("",)]

    def test_rm_sub(self, script_runner):
        result, _ = script_runner("""
            -- !x! sub myvar hello
            -- !x! rm_sub myvar
            create table t_ok (id integer);
        """)
        assert result.exit_code == 0, result.output

    def test_sub_tempfile(self, script_runner):
        result, db = script_runner("""
            -- !x! sub_tempfile tmpf
            create table result (val text);
            insert into result values ('!!tmpf!!');
        """)
        assert result.exit_code == 0, result.output
        rows = qdb(db, "SELECT val FROM result")
        content = rows[0][0]
        assert content != ""
        assert content != "!!tmpf!!"

    def test_sub_querystring(self, script_runner):
        result, db = script_runner("""
            -- !x! sub_querystring foo=bar&baz=qux
            create table result (val text);
            insert into result values ('!!foo!!');
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT val FROM result") == [("bar",)]

    def test_sub_ini(self, script_runner, tmp_path):
        ini_file = tmp_path / "config.ini"
        ini_file.write_text("[mysection]\ncolor = blue\nsize = large\n")
        result, db = script_runner(f"""
            -- !x! sub_ini {ini_file} mysection
            create table result (val text);
            insert into result values ('!!color!!');
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT val FROM result") == [("blue",)]

    def test_subdata(self, script_runner):
        """SUBDATA sets varname to the value of the FIRST CELL (first col, first row)."""
        result, db = script_runner("""
            create table singleval (val text);
            insert into singleval values ('hello');
            -- !x! subdata myvar singleval
            create table result (v text);
            insert into result values ('!!myvar!!');
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT v FROM result") == [("hello",)]

    def test_select_sub(self, script_runner):
        """SELECT_SUB sets variables named by column headers (with @ prefix)."""
        result, db = script_runner("""
            create table greeting (msg text, who text);
            insert into greeting values ('hello', 'world');
            -- !x! select_sub greeting
            create table result (v text);
            insert into result values ('!!@msg!!');
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT v FROM result") == [("hello",)]


# ---------------------------------------------------------------------------
# Control-flow metacommands
# ---------------------------------------------------------------------------


class TestControlFlow:
    """IF/ENDIF, ELSEIF, ELSE, ORIF, ANDIF, inline IF, LOOP, BREAK, HALT."""

    def test_if_true(self, script_runner):
        result, db = script_runner("""
            -- !x! sub flag 1
            -- !x! if (equals(!!flag!!, 1))
            create table t_true (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_true")

    def test_if_false(self, script_runner):
        result, db = script_runner("""
            -- !x! sub flag 0
            -- !x! if (equals(!!flag!!, 1))
            create table t_should_not_exist (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert not table_exists(db, "t_should_not_exist")

    def test_if_else_true_branch(self, script_runner):
        result, db = script_runner("""
            -- !x! sub flag yes
            -- !x! if (equals(!!flag!!, yes))
            create table t_yes (id integer);
            -- !x! else
            create table t_no (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_yes")
        assert not table_exists(db, "t_no")

    def test_if_else_false_branch(self, script_runner):
        result, db = script_runner("""
            -- !x! sub flag no
            -- !x! if (equals(!!flag!!, yes))
            create table t_yes (id integer);
            -- !x! else
            create table t_no (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert not table_exists(db, "t_yes")
        assert table_exists(db, "t_no")

    def test_elseif(self, script_runner):
        result, db = script_runner("""
            -- !x! sub color blue
            -- !x! if (equals(!!color!!, red))
            create table t_red (id integer);
            -- !x! elseif (equals(!!color!!, blue))
            create table t_blue (id integer);
            -- !x! else
            create table t_other (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert not table_exists(db, "t_red")
        assert table_exists(db, "t_blue")
        assert not table_exists(db, "t_other")

    def test_orif(self, script_runner):
        result, db = script_runner("""
            -- !x! sub x 0
            -- !x! sub y 1
            -- !x! if (equals(!!x!!, 1))
            -- !x! orif (equals(!!y!!, 1))
            create table t_orif (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_orif")

    def test_andif(self, script_runner):
        result, db = script_runner("""
            -- !x! sub x 1
            -- !x! sub y 1
            -- !x! if (equals(!!x!!, 1))
            -- !x! andif (equals(!!y!!, 1))
            create table t_andif (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_andif")

    def test_andif_fails_when_second_false(self, script_runner):
        result, db = script_runner("""
            -- !x! sub x 1
            -- !x! sub y 0
            -- !x! if (equals(!!x!!, 1))
            -- !x! andif (equals(!!y!!, 1))
            create table t_andif_fail (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert not table_exists(db, "t_andif_fail")

    def test_inline_if(self, script_runner):
        """IF (cond) { cmd } inline form."""
        result, db = script_runner("""
            -- !x! if (equals(1, 1)) { sub myvar inline_worked }
            create table t_inline (id integer);
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_inline")

    def test_nested_if(self, script_runner):
        result, db = script_runner("""
            -- !x! sub outer 1
            -- !x! if (equals(!!outer!!, 1))
            -- !x! sub inner 1
            -- !x! if (equals(!!inner!!, 1))
            create table t_nested (id integer);
            -- !x! endif
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_nested")

    def test_loop_while(self, script_runner):
        result, db = script_runner("""
            -- !x! sub counter 0
            -- !x! loop while (not is_gte(!{counter}!, 5))
            -- !x! sub_add counter 1
            -- !x! end loop
            create table t_loop (n integer);
            insert into t_loop values (!!counter!!);
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT n FROM t_loop") == [(5,)]

    def test_loop_until(self, script_runner):
        result, db = script_runner("""
            -- !x! sub counter 0
            -- !x! loop until (equals(!{counter}!, 3))
            -- !x! sub_add counter 1
            -- !x! end loop
            create table t_until (n integer);
            insert into t_until values (!!counter!!);
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT n FROM t_until") == [(3,)]

    def test_error_halt_off_continues_after_error(self, script_runner):
        """ERROR_HALT OFF lets SQL errors pass without stopping script."""
        result, db = script_runner("""
            -- !x! error_halt off
            select * from nonexistent_table_xyz;
            create table t_after_error (id integer);
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_after_error")

    def test_error_halt_on_stops_on_sql_error(self, script_runner):
        result, _ = script_runner("""
            -- !x! error_halt on
            select * from nonexistent_table_xyz;
        """)
        assert result.exit_code != 0

    def test_metacommand_error_halt_off(self, script_runner):
        result, _ = script_runner("""
            -- !x! metacommand_error_halt off
        """)
        assert result.exit_code == 0, result.output

    def test_halt_exits_nonzero(self, script_runner):
        # Use halt without a message to avoid triggering the GUI dialog path
        # (HALT MESSAGE "..." dispatches to x_halt_msg which blocks on user input)
        result, _ = script_runner("""
            -- !x! halt exit_status 1
        """)
        assert result.exit_code != 0

    def test_halt_exit_status(self, script_runner):
        result, _ = script_runner("""
            -- !x! halt exit_status 2
        """)
        assert result.exit_code != 0

    def test_begin_end_batch(self, script_runner):
        result, db = script_runner("""
            -- !x! begin batch
            create table t_batch (id integer);
            insert into t_batch values (1);
            -- !x! end batch
        """)
        assert result.exit_code == 0, result.output
        rows = qdb(db, "SELECT id FROM t_batch")
        assert rows == [(1,)]

    def test_cancel_halt_flag(self, script_runner):
        result, _ = script_runner("""
            -- !x! cancel_halt on
            -- !x! cancel_halt off
        """)
        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# WRITE / IO metacommands
# ---------------------------------------------------------------------------


class TestWriteIO:
    """WRITE, WRITE to file, INCLUDE, CD."""

    def test_write_to_console(self, script_runner):
        result, _ = script_runner("""
            -- !x! write "hello from execsql"
        """)
        assert result.exit_code == 0, result.output
        assert "hello from execsql" in result.output

    def test_write_to_file(self, script_runner, tmp_path):
        out = tmp_path / "output.txt"
        result, _ = script_runner(f"""
            -- !x! write "hello file" to {out}
        """)
        assert result.exit_code == 0, result.output
        assert out.exists()
        assert "hello file" in out.read_text()

    def test_write_tee(self, script_runner, tmp_path):
        out = tmp_path / "output.txt"
        result, _ = script_runner(f"""
            -- !x! write "tee message" tee to {out}
        """)
        assert result.exit_code == 0, result.output
        assert "tee message" in result.output
        assert out.exists()

    def test_write_with_substitution_in_console(self, script_runner):
        result, _ = script_runner("""
            -- !x! sub name world
            -- !x! write "hello !!name!!"
        """)
        assert result.exit_code == 0, result.output
        assert "hello world" in result.output

    def test_include(self, script_runner, tmp_path):
        included = tmp_path / "sub.sql"
        included.write_text("create table t_included (id integer);\n")
        result, db = script_runner(f"""
            -- !x! include {included}
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_included")

    def test_include_if_exists_missing(self, script_runner):
        result, _ = script_runner("""
            -- !x! include if exists /nonexistent/path/missing.sql
        """)
        assert result.exit_code == 0, result.output

    def test_cd(self, script_runner, tmp_path):
        result, _ = script_runner(f"""
            -- !x! cd {tmp_path}
        """)
        assert result.exit_code == 0, result.output

    def test_write_prefix(self, script_runner):
        result, _ = script_runner("""
            -- !x! config write_prefix >>
            -- !x! write "message"
        """)
        assert result.exit_code == 0, result.output
        assert ">>" in result.output

    def test_write_suffix(self, script_runner):
        result, _ = script_runner("""
            -- !x! config write_suffix <<
            -- !x! write "message"
        """)
        assert result.exit_code == 0, result.output
        assert "<<" in result.output


# ---------------------------------------------------------------------------
# EXPORT / IMPORT metacommands
# ---------------------------------------------------------------------------


class TestExportImport:
    """EXPORT table AS format, EXPORT QUERY, IMPORT FROM."""

    _table_sql = """
        create table t1 (id integer, name text, val real);
        insert into t1 values (1, 'alpha', 1.5);
        insert into t1 values (2, 'beta',  2.5);
    """

    def test_export_csv(self, script_runner, tmp_path):
        out = tmp_path / "out.csv"
        result, _ = script_runner(f"""
            {self._table_sql}
            -- !x! export t1 to {out} as csv
        """)
        assert result.exit_code == 0, result.output
        assert out.exists()
        rows = list(csv.reader(out.read_text().splitlines()))
        assert len(rows) == 3  # header + 2 data rows

    def test_export_txt(self, script_runner, tmp_path):
        out = tmp_path / "out.txt"
        result, _ = script_runner(f"""
            {self._table_sql}
            -- !x! export t1 to {out} as txt
        """)
        assert result.exit_code == 0, result.output
        assert out.exists()
        content = out.read_text()
        assert "alpha" in content

    def test_export_json(self, script_runner, tmp_path):
        out = tmp_path / "out.json"
        result, _ = script_runner(f"""
            {self._table_sql}
            -- !x! export t1 to {out} as json
        """)
        assert result.exit_code == 0, result.output
        assert out.exists()
        data = json.loads(out.read_text())
        assert isinstance(data, list)
        assert len(data) == 2

    def test_export_tsv(self, script_runner, tmp_path):
        out = tmp_path / "out.tsv"
        result, _ = script_runner(f"""
            {self._table_sql}
            -- !x! export t1 to {out} as tsv
        """)
        assert result.exit_code == 0, result.output
        assert out.exists()

    def test_export_query_csv(self, script_runner, tmp_path):
        out = tmp_path / "query.csv"
        result, _ = script_runner(f"""
            {self._table_sql}
            -- !x! export query << select id, name from t1; >> to {out} as csv
        """)
        assert result.exit_code == 0, result.output
        assert out.exists()
        rows = list(csv.reader(out.read_text().splitlines()))
        assert len(rows) == 3  # header + 2 rows

    def test_export_query_json(self, script_runner, tmp_path):
        out = tmp_path / "query.json"
        result, _ = script_runner(f"""
            {self._table_sql}
            -- !x! export query << select id from t1 where id = 1; >> to {out} as json
        """)
        assert result.exit_code == 0, result.output
        data = json.loads(out.read_text())
        assert len(data) == 1
        assert data[0]["id"] == 1

    def test_export_append(self, script_runner, tmp_path):
        out = tmp_path / "append.csv"
        result, _ = script_runner(f"""
            {self._table_sql}
            -- !x! export t1 to {out} as csv
            -- !x! export t1 append to {out} as csv
        """)
        assert result.exit_code == 0, result.output
        lines = out.read_text().strip().splitlines()
        # header + 2 data + 2 data (append skips header) = 5
        assert len(lines) >= 4

    def test_export_tee(self, script_runner, tmp_path):
        out = tmp_path / "tee.csv"
        result, _ = script_runner(f"""
            {self._table_sql}
            -- !x! export t1 tee to {out} as csv
        """)
        assert result.exit_code == 0, result.output
        assert out.exists()

    def test_import_csv(self, script_runner, tmp_path):
        csv_file = tmp_path / "import.csv"
        csv_file.write_text("id,name\n1,alpha\n2,beta\n")
        result, db = script_runner(f"""
            -- !x! import to new t_imported from {csv_file}
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_imported")
        rows = qdb(db, "SELECT id, name FROM t_imported ORDER BY id")
        assert len(rows) == 2

    def test_import_csv_tab_delimiter(self, script_runner, tmp_path):
        tsv_file = tmp_path / "import.tsv"
        tsv_file.write_text("id\tname\n1\talpha\n2\tbeta\n")
        result, db = script_runner(
            f"""
            -- !x! import to new t_tsv from {tsv_file} with quote none delimiter tab
        """,
        )
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_tsv")

    def test_rm_file(self, script_runner, tmp_path):
        victim = tmp_path / "todelete.txt"
        victim.write_text("delete me")
        result, _ = script_runner(f"""
            -- !x! rm_file {victim}
        """)
        assert result.exit_code == 0, result.output
        assert not victim.exists()

    def test_make_export_dirs(self, script_runner, tmp_path):
        out_dir = tmp_path / "subdir" / "deep"
        out_file = out_dir / "out.csv"
        result, _ = script_runner(f"""
            create table t1 (id integer);
            insert into t1 values (1);
            -- !x! config make_export_dirs yes
            -- !x! export t1 to {out_file} as csv
        """)
        assert result.exit_code == 0, result.output
        assert out_file.exists()


# ---------------------------------------------------------------------------
# Conditions (xf_* predicate functions)
# ---------------------------------------------------------------------------


class TestConditions:
    """IF using xf_* predicates: tableexists, fileexists, hasrows, etc."""

    def test_xf_tableexists_true(self, script_runner):
        result, db = script_runner("""
            create table lookup (id integer);
            -- !x! if (table_exists(lookup))
            create table t_tableexists (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_tableexists")

    def test_xf_tableexists_false(self, script_runner):
        result, db = script_runner("""
            -- !x! if (table_exists(nonexistent_xyz))
            create table t_should_not_exist (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert not table_exists(db, "t_should_not_exist")

    def test_xf_hasrows_true(self, script_runner):
        result, db = script_runner("""
            create table data (id integer);
            insert into data values (1);
            -- !x! if (hasrows(data))
            create table t_hasrows (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_hasrows")

    def test_xf_hasrows_false(self, script_runner):
        result, db = script_runner("""
            create table empty_tbl (id integer);
            -- !x! if (hasrows(empty_tbl))
            create table t_norows (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert not table_exists(db, "t_norows")

    def test_xf_fileexists_true(self, script_runner, tmp_path):
        f = tmp_path / "exists.txt"
        f.write_text("here")
        result, db = script_runner(f"""
            -- !x! if (file_exists({f}))
            create table t_fileexists (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_fileexists")

    def test_xf_fileexists_false(self, script_runner):
        result, db = script_runner("""
            -- !x! if (file_exists(/no/such/file/xyz.txt))
            create table t_nofile (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert not table_exists(db, "t_nofile")

    def test_xf_contains(self, script_runner):
        result, db = script_runner("""
            -- !x! sub sentence hello_world
            -- !x! if (contains(!!sentence!!, world))
            create table t_contains (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_contains")

    def test_xf_startswith(self, script_runner):
        result, db = script_runner("""
            -- !x! sub word hello
            -- !x! if (starts_with(!!word!!, hel))
            create table t_starts (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_starts")

    def test_xf_endswith(self, script_runner):
        result, db = script_runner("""
            -- !x! sub word hello
            -- !x! if (ends_with(!!word!!, llo))
            create table t_ends (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_ends")

    def test_xf_sub_defined(self, script_runner):
        result, db = script_runner("""
            -- !x! sub myvar defined_value
            -- !x! if (sub_defined(myvar))
            create table t_sub_defined (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_sub_defined")

    def test_xf_sqlerror_false_when_no_error(self, script_runner):
        result, db = script_runner("""
            -- !x! error_halt off
            create table t_ok (id integer);
            -- !x! if (sql_error())
            create table t_had_error (id integer);
            -- !x! else
            create table t_no_error (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert not table_exists(db, "t_had_error")
        assert table_exists(db, "t_no_error")

    def test_xf_contains_ignorecase(self, script_runner):
        result, db = script_runner("""
            -- !x! sub sentence Hello_World
            -- !x! if (contains(!!sentence!!, "world", I))
            create table t_contains_i (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_contains_i")

    def test_xf_startswith_ignorecase(self, script_runner):
        result, db = script_runner("""
            -- !x! sub word Hello
            -- !x! if (starts_with(!!word!!, "hel", I))
            create table t_starts_i (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_starts_i")

    def test_xf_endswith_ignorecase(self, script_runner):
        result, db = script_runner("""
            -- !x! sub word Hello
            -- !x! if (ends_with(!!word!!, "LLO", I))
            create table t_ends_i (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_ends_i")

    def test_xf_direxists_true(self, script_runner, tmp_path):
        result, db = script_runner(f"""
            -- !x! if (directory_exists("{tmp_path}"))
            create table t_direxists (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_direxists")

    def test_xf_direxists_false(self, script_runner):
        result, db = script_runner("""
            -- !x! if (directory_exists("/no/such/directory/xyz"))
            create table t_no_dir (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert not table_exists(db, "t_no_dir")

    def test_xf_equals_strings(self, script_runner):
        result, db = script_runner("""
            -- !x! sub a hello
            -- !x! sub b hello
            -- !x! if (equals(!!a!!, !!b!!))
            create table t_equals (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_equals")

    def test_xf_equals_numbers(self, script_runner):
        result, db = script_runner("""
            -- !x! sub a 42
            -- !x! sub b 42
            -- !x! if (equals(!!a!!, !!b!!))
            create table t_equals_num (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_equals_num")

    def test_xf_identical_true(self, script_runner):
        result, db = script_runner("""
            -- !x! sub a Hello
            -- !x! sub b Hello
            -- !x! if (identical(!!a!!, !!b!!))
            create table t_identical (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_identical")

    def test_xf_identical_case_sensitive(self, script_runner):
        result, db = script_runner("""
            -- !x! sub a Hello
            -- !x! sub b hello
            -- !x! if (identical(!!a!!, !!b!!))
            create table t_ident_case (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert not table_exists(db, "t_ident_case")

    def test_xf_isnull_true(self, script_runner):
        result, db = script_runner("""
            -- !x! if (is_null(""))
            create table t_isnull (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_isnull")

    def test_xf_iszero_true(self, script_runner):
        result, db = script_runner("""
            -- !x! sub val 0
            -- !x! if (is_zero(!!val!!))
            create table t_iszero (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_iszero")

    def test_xf_iszero_false(self, script_runner):
        result, db = script_runner("""
            -- !x! sub val 5
            -- !x! if (is_zero(!!val!!))
            create table t_not_zero (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert not table_exists(db, "t_not_zero")

    def test_xf_isgt_true(self, script_runner):
        result, db = script_runner("""
            -- !x! if (is_gt(10, 5))
            create table t_isgt (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_isgt")

    def test_xf_isgt_false(self, script_runner):
        result, db = script_runner("""
            -- !x! if (is_gt(5, 10))
            create table t_not_gt (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert not table_exists(db, "t_not_gt")

    def test_xf_isgte_equal(self, script_runner):
        result, db = script_runner("""
            -- !x! if (is_gte(5, 5))
            create table t_isgte (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_isgte")

    def test_xf_boolliteral_true(self, script_runner):
        result, db = script_runner("""
            -- !x! if (True)
            create table t_booltrue (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_booltrue")

    def test_xf_boolliteral_false(self, script_runner):
        result, db = script_runner("""
            -- !x! if (False)
            create table t_boolfalse (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert not table_exists(db, "t_boolfalse")

    def test_xf_istrue_yes(self, script_runner):
        result, db = script_runner("""
            -- !x! sub flag yes
            -- !x! if (is_true(!!flag!!))
            create table t_istrue (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_istrue")

    def test_xf_istrue_false(self, script_runner):
        result, db = script_runner("""
            -- !x! sub flag no
            -- !x! if (is_true(!!flag!!))
            create table t_isfalse (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert not table_exists(db, "t_isfalse")

    def test_xf_metacommanderror_false_when_no_error(self, script_runner):
        result, db = script_runner("""
            -- !x! if (metacommand_error())
            create table t_mcerr (id integer);
            -- !x! else
            create table t_no_mcerr (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert not table_exists(db, "t_mcerr")
        assert table_exists(db, "t_no_mcerr")

    def test_xf_console_off_at_level_0(self, script_runner):
        result, db = script_runner("""
            -- !x! if (console_on)
            create table t_console_on (id integer);
            -- !x! else
            create table t_console_off (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert not table_exists(db, "t_console_on")
        assert table_exists(db, "t_console_off")

    def test_xf_sub_empty_false_when_nonempty(self, script_runner):
        result, db = script_runner("""
            -- !x! sub filledvar hello
            -- !x! if (sub_empty(filledvar))
            create table t_sub_empty (id integer);
            -- !x! else
            create table t_sub_notempty (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert not table_exists(db, "t_sub_empty")
        assert table_exists(db, "t_sub_notempty")

    def test_xf_script_exists_false(self, script_runner):
        result, db = script_runner("""
            -- !x! if (script_exists(no_such_script))
            create table t_script_exists (id integer);
            -- !x! else
            create table t_no_script (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert not table_exists(db, "t_script_exists")
        assert table_exists(db, "t_no_script")

    def test_xf_newer_file(self, script_runner, tmp_path):
        import time

        older = tmp_path / "older.txt"
        older.write_text("old")
        time.sleep(0.05)
        newer = tmp_path / "newer.txt"
        newer.write_text("new")
        result, db = script_runner(f"""
            -- !x! if (newer_file({newer}, {older}))
            create table t_newer (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_newer")


# ---------------------------------------------------------------------------
# Unit tests for conditions.py utilities
# ---------------------------------------------------------------------------


class TestConditionsUtilities:
    """Unit tests for xcmd_test(), chainfuncs(), and as_none()."""

    def test_as_none_empty_string(self):
        from execsql.metacommands.conditions import as_none

        assert as_none("") is None

    def test_as_none_nonempty_string(self):
        from execsql.metacommands.conditions import as_none

        assert as_none("hello") == "hello"

    def test_as_none_zero_int(self):
        from execsql.metacommands.conditions import as_none

        assert as_none(0) is None

    def test_as_none_nonzero_int(self):
        from execsql.metacommands.conditions import as_none

        assert as_none(42) == 42

    def test_as_none_other_type(self):
        from execsql.metacommands.conditions import as_none

        assert as_none(3.14) == 3.14

    def test_chainfuncs_calls_all(self):
        from execsql.metacommands.conditions import chainfuncs

        calls = []

        def f1():
            calls.append(1)

        def f2():
            calls.append(2)

        chain = chainfuncs(f1, f2)
        chain()
        assert calls == [1, 2]

    def test_chainfuncs_returns_callable(self):
        from execsql.metacommands.conditions import chainfuncs

        chain = chainfuncs(lambda: None)
        assert callable(chain)


class TestConditionsErrorPaths:
    """Error-path coverage for xf_* predicates that raise ErrInfo."""

    def setup_method(self):
        """Set up minimal _state for unit tests."""
        import execsql.state as _state
        from types import SimpleNamespace

        if _state.conf is None:
            _state.conf = SimpleNamespace(
                boolean_int=True,
                boolean_words=False,
                max_int=2_147_483_647,
                only_strings=False,
                trim_strings=False,
                replace_newlines=False,
                empty_strings=True,
                del_empty_cols=False,
                output_encoding="utf-8",
                make_export_dirs=False,
                enc_err_disposition=None,
                gui_level=0,
                gui_framework="tkinter",
                gui_wait_on_exit=False,
                gui_wait_on_error_halt=False,
            )

    def test_xf_iszero_nonnumeric_raises(self):
        from execsql.metacommands.conditions import xf_iszero
        import execsql.state as _state

        with pytest.raises(ErrInfo):
            xf_iszero(value="notanumber", metacommandline="is_zero(notanumber)")

    def test_xf_isgt_nonnumeric_raises(self):
        from execsql.metacommands.conditions import xf_isgt
        import execsql.state as _state

        with pytest.raises(ErrInfo):
            xf_isgt(value1="abc", value2="5", metacommandline="is_gt(abc, 5)")

    def test_xf_isgte_nonnumeric_raises(self):
        from execsql.metacommands.conditions import xf_isgte
        import execsql.state as _state

        with pytest.raises(ErrInfo):
            xf_isgte(value1="abc", value2="5", metacommandline="is_gte(abc, 5)")

    def test_xf_newer_file_missing_file1_raises(self, tmp_path):
        from execsql.metacommands.conditions import xf_newer_file
        import execsql.state as _state

        existing = tmp_path / "exists.txt"
        existing.write_text("here")
        with pytest.raises(ErrInfo):
            xf_newer_file(file1="/no/such/file.txt", file2=str(existing))

    def test_xf_newer_file_missing_file2_raises(self, tmp_path):
        from execsql.metacommands.conditions import xf_newer_file
        import execsql.state as _state

        existing = tmp_path / "exists.txt"
        existing.write_text("here")
        with pytest.raises(ErrInfo):
            xf_newer_file(file1=str(existing), file2="/no/such/file.txt")

    def test_xf_newer_date_missing_file_raises(self):
        from execsql.metacommands.conditions import xf_newer_date
        import execsql.state as _state

        with pytest.raises(ErrInfo):
            xf_newer_date(file1="/no/such/file.txt", datestr="2020-01-01")

    def test_xf_newer_date_invalid_date_raises(self, tmp_path):
        from execsql.metacommands.conditions import xf_newer_date
        import execsql.state as _state

        f = tmp_path / "f.txt"
        f.write_text("data")
        with pytest.raises(ErrInfo):
            xf_newer_date(file1=str(f), datestr="not-a-date")


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------


class TestCounters:
    """RESET COUNTER, RESET COUNTERS, SET COUNTER."""

    def test_reset_counter(self, script_runner):
        result, _ = script_runner("""
            -- !x! reset counter 1
        """)
        assert result.exit_code == 0, result.output

    def test_reset_counters(self, script_runner):
        result, _ = script_runner("""
            -- !x! reset counters
        """)
        assert result.exit_code == 0, result.output

    def test_set_counter(self, script_runner):
        # Counter auto-increments on each reference: set to 42, first use returns 43.
        result, db = script_runner("""
            -- !x! set counter 1 to 42
            create table t_counter (n integer);
            insert into t_counter values (!!$counter_1!!);
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT n FROM t_counter") == [(43,)]


# ---------------------------------------------------------------------------
# System / LOG / TIMER / CONFIG
# ---------------------------------------------------------------------------


class TestSystem:
    """LOG, TIMER, SYSTEM_CMD, AUTOCOMMIT, CONSOLE, CONFIG.*."""

    def test_log_message(self, script_runner):
        result, _ = script_runner("""
            -- !x! log "integration test log message"
        """)
        assert result.exit_code == 0, result.output

    def test_timer_on_off(self, script_runner):
        result, _ = script_runner("""
            -- !x! timer on
            -- !x! timer off
        """)
        assert result.exit_code == 0, result.output

    def test_system_cmd(self, script_runner):
        result, _ = script_runner("""
            -- !x! system_cmd (echo execsql_test) continue
        """)
        assert result.exit_code == 0, result.output

    def test_autocommit_on(self, script_runner):
        result, _ = script_runner("""
            -- !x! autocommit on
        """)
        assert result.exit_code == 0, result.output

    def test_autocommit_off(self, script_runner):
        result, _ = script_runner("""
            -- !x! autocommit off
        """)
        assert result.exit_code == 0, result.output

    def test_config_empty_strings(self, script_runner):
        result, _ = script_runner("""
            -- !x! config empty_strings yes
            -- !x! config empty_strings no
        """)
        assert result.exit_code == 0, result.output

    def test_config_trim_strings(self, script_runner):
        result, _ = script_runner("""
            -- !x! config trim_strings yes
            -- !x! config trim_strings no
        """)
        assert result.exit_code == 0, result.output

    def test_config_replace_newlines(self, script_runner):
        result, _ = script_runner("""
            -- !x! config replace_newlines yes
        """)
        assert result.exit_code == 0, result.output

    def test_config_only_strings(self, script_runner):
        result, _ = script_runner("""
            -- !x! config only_strings yes
            -- !x! config only_strings no
        """)
        assert result.exit_code == 0, result.output

    def test_config_boolean_int(self, script_runner):
        result, _ = script_runner("""
            -- !x! boolean_int yes
            -- !x! boolean_int no
        """)
        assert result.exit_code == 0, result.output

    def test_config_boolean_words(self, script_runner):
        result, _ = script_runner("""
            -- !x! config boolean_words yes
        """)
        assert result.exit_code == 0, result.output

    def test_config_fold_column_headers(self, script_runner):
        result, _ = script_runner("""
            -- !x! config fold_column_headers lower
            -- !x! config fold_column_headers upper
            -- !x! config fold_column_headers no
        """)
        assert result.exit_code == 0, result.output

    def test_config_gui_level(self, script_runner):
        result, _ = script_runner("""
            -- !x! config gui_level 0
        """)
        assert result.exit_code == 0, result.output

    def test_console_on_off(self, script_runner):
        result, _ = script_runner("""
            -- !x! console on
            -- !x! console off
        """)
        assert result.exit_code == 0, result.output

    def test_console_status(self, script_runner):
        result, _ = script_runner("""
            -- !x! console on
            -- !x! console status "running tests"
            -- !x! console off
        """)
        assert result.exit_code == 0, result.output

    def test_console_progress(self, script_runner):
        result, _ = script_runner("""
            -- !x! console on
            -- !x! console progress 50 / 100
            -- !x! console off
        """)
        assert result.exit_code == 0, result.output

    def test_error_halt_write(self, script_runner, tmp_path):
        out = tmp_path / "err.txt"
        result, _ = script_runner(f"""
            -- !x! on error_halt write "an error occurred" to {out}
        """)
        assert result.exit_code == 0, result.output

    def test_error_halt_write_clear(self, script_runner):
        result, _ = script_runner("""
            -- !x! on error_halt write clear
        """)
        assert result.exit_code == 0, result.output

    def test_cancel_halt_write(self, script_runner, tmp_path):
        out = tmp_path / "cancel.txt"
        result, _ = script_runner(f"""
            -- !x! on cancel_halt write "cancelled" to {out}
        """)
        assert result.exit_code == 0, result.output

    def test_cancel_halt_write_clear(self, script_runner):
        result, _ = script_runner("""
            -- !x! on cancel_halt write clear
        """)
        assert result.exit_code == 0, result.output

    def test_config_write_warnings(self, script_runner):
        result, _ = script_runner("""
            -- !x! config write_warnings yes
            -- !x! config write_warnings no
        """)
        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# Debug metacommands
# ---------------------------------------------------------------------------


class TestDebug:
    """DEBUG WRITE COMMANDLISTSTACK, DEBUG WRITE IFLEVELS,
    DEBUG LOG SUBVARS, DEBUG LOG CONFIG, DEBUG WRITE SUBVARS."""

    def test_debug_commandliststack(self, script_runner):
        result, _ = script_runner("""
            -- !x! debug write commandliststack
        """)
        assert result.exit_code == 0, result.output

    def test_debug_iflevels(self, script_runner):
        result, _ = script_runner("""
            -- !x! debug write iflevels
        """)
        assert result.exit_code == 0, result.output

    def test_debug_log_subvars(self, script_runner):
        result, _ = script_runner("""
            -- !x! sub testvar hello
            -- !x! debug log subvars
        """)
        assert result.exit_code == 0, result.output

    def test_debug_log_config(self, script_runner):
        result, _ = script_runner("""
            -- !x! debug log config
        """)
        assert result.exit_code == 0, result.output

    def test_debug_write_subvars(self, script_runner, tmp_path):
        out = tmp_path / "subvars.txt"
        result, _ = script_runner(f"""
            -- !x! sub myvar hello
            -- !x! debug write subvars to {out}
        """)
        assert result.exit_code == 0, result.output
        assert out.exists()
        assert "myvar" in out.read_text()

    def test_debug_write_config(self, script_runner, tmp_path):
        out = tmp_path / "config_dump.txt"
        result, _ = script_runner(f"""
            -- !x! debug write config to {out}
        """)
        assert result.exit_code == 0, result.output
        assert out.exists()

    def test_debug_write_metacommandlist(self, script_runner, tmp_path):
        out = tmp_path / "mcl.txt"
        result, _ = script_runner(f"""
            -- !x! debug write metacommandlist to {out}
        """)
        assert result.exit_code == 0, result.output
        assert out.exists()


# ---------------------------------------------------------------------------
# Connect metacommands
# ---------------------------------------------------------------------------


class TestConnect:
    """CONNECT TO SQLITE (second database), USE, DISCONNECT."""

    def test_connect_sqlite_second_db(self, script_runner, tmp_path):
        second_db = tmp_path / "second.db"
        result, _ = script_runner(f"""
            -- !x! connect to sqlite(file={second_db}, new) as DB2
            -- !x! use DB2
            create table t_in_second (id integer);
            -- !x! disconnect from DB2
        """)
        assert result.exit_code == 0, result.output
        assert second_db.exists()
        assert table_exists(second_db, "t_in_second")

    def test_use_switches_db(self, script_runner, tmp_path):
        second_db = tmp_path / "second.db"
        result, _ = script_runner(f"""
            -- !x! connect to sqlite(file={second_db}, new) as DB2
            -- !x! use DB2
            create table t_second (id integer);
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(second_db, "t_second")

    def test_disconnect(self, script_runner, tmp_path):
        second_db = tmp_path / "disc.db"
        result, _ = script_runner(f"""
            -- !x! connect to sqlite(file={second_db}, new) as DISC
            -- !x! disconnect from DISC
        """)
        assert result.exit_code == 0, result.output

    def test_autocommit_toggle(self, script_runner):
        result, db = script_runner("""
            -- !x! autocommit on with commit
            create table t_ac (id integer);
            insert into t_ac values (1);
            -- !x! autocommit off
        """)
        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# Named scripts (BEGIN/END SCRIPT, RUN SCRIPT)
# ---------------------------------------------------------------------------


class TestNamedScripts:
    """BEGIN SCRIPT … END SCRIPT and RUN SCRIPT."""

    def test_begin_end_run_script(self, script_runner):
        result, db = script_runner("""
            -- !x! begin script myscript
            create table t_from_script (id integer);
            insert into t_from_script values (99);
            -- !x! end script
            -- !x! run script myscript
        """)
        assert result.exit_code == 0, result.output
        rows = qdb(db, "SELECT id FROM t_from_script")
        assert rows == [(99,)]

    def test_script_run_multiple_times(self, script_runner):
        result, db = script_runner("""
            create table counter_tbl (n integer);
            -- !x! begin script addrow
            insert into counter_tbl values (1);
            -- !x! end script
            -- !x! run script addrow
            -- !x! run script addrow
            -- !x! run script addrow
        """)
        assert result.exit_code == 0, result.output
        rows = qdb(db, "SELECT count(*) FROM counter_tbl")
        assert rows == [(3,)]


# ---------------------------------------------------------------------------
# PAUSE (headless — should print and continue / halt)
# ---------------------------------------------------------------------------


class TestPause:
    """PAUSE in headless mode should not block."""

    def test_pause_continue_after_timeout(self, script_runner):
        result, db = script_runner("""
            -- !x! pause "short pause" continue after 1 seconds
            create table t_after_pause (id integer);
        """)
        assert result.exit_code == 0, result.output
        assert table_exists(db, "t_after_pause")

    def test_pause_halt_after_timeout(self, script_runner):
        result, _ = script_runner("""
            -- !x! pause "will halt" halt after 1 seconds
        """)
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# RESET_DIALOG_CANCELED
# ---------------------------------------------------------------------------


class TestDialogCanceled:
    def test_reset_dialog_canceled(self, script_runner):
        result, _ = script_runner("""
            -- !x! reset dialog_canceled
        """)
        assert result.exit_code == 0, result.output

    def test_xf_dialogcanceled_false_initially(self, script_runner):
        result, db = script_runner("""
            -- !x! if (dialog_canceled())
            create table t_canceled (id integer);
            -- !x! else
            create table t_not_canceled (id integer);
            -- !x! endif
        """)
        assert result.exit_code == 0, result.output
        assert not table_exists(db, "t_canceled")
        assert table_exists(db, "t_not_canceled")


# ---------------------------------------------------------------------------
# BREAK metacommand
# ---------------------------------------------------------------------------


class TestBreak:
    def test_break_in_loop(self, script_runner):
        result, db = script_runner("""
            -- !x! sub counter 0
            -- !x! loop while (not is_gte(!{counter}!, 100))
            -- !x! sub_add counter 1
            -- !x! if (equals(!!counter!!, 3))
            -- !x! break
            -- !x! endif
            -- !x! end loop
            create table t_break (n integer);
            insert into t_break values (!!counter!!);
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT n FROM t_break") == [(3,)]

    def test_break_at_top_level_warns(self, script_runner):
        """BREAK outside a loop emits a warning but does not crash."""
        result, _ = script_runner("""
            -- !x! break
        """)
        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# WAIT_UNTIL (short timeout)
# ---------------------------------------------------------------------------


class TestWaitUntil:
    def test_wait_until_condition_already_true(self, script_runner):
        result, _ = script_runner("""
            -- !x! sub flag 1
            -- !x! wait_until (equals(!!flag!!, 1)) continue after 2 seconds
        """)
        assert result.exit_code == 0, result.output

    def test_wait_until_timeout_halt(self, script_runner):
        result, _ = script_runner("""
            -- !x! sub flag 0
            -- !x! wait_until (equals(!!flag!!, 1)) halt after 1 seconds
        """)
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# MAX_INT
# ---------------------------------------------------------------------------


class TestMaxInt:
    def test_max_int(self, script_runner):
        result, _ = script_runner("""
            -- !x! max_int 9999999
        """)
        assert result.exit_code == 0, result.output
