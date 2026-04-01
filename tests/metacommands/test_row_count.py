"""Tests for ROW_COUNT_GT/GTE/EQ/LT conditional predicates.

Covers:
- Unit tests for each predicate function (mocked DB) — correct comparisons
- _row_count helper raises ErrInfo on DB failure
- _parse_row_count_n raises ErrInfo for non-integer threshold
- Dispatch regex correctly matches ROW_COUNT_GT/GTE/EQ/LT syntax variants
- Integration tests via SQLite: true and false conditions inside IF/ASSERT
"""

from __future__ import annotations

import sqlite3
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

import execsql.state as _state
from execsql.cli import app
from execsql.exceptions import ErrInfo
from execsql.metacommands.conditions import (
    _parse_row_count_n,
    _row_count,
    xf_row_count_eq,
    xf_row_count_gt,
    xf_row_count_gte,
    xf_row_count_lt,
)

_runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_db_with_count(n: int) -> MagicMock:
    """Return a mock database whose select_data always returns count *n*."""
    db = MagicMock()
    db.select_data.return_value = (["count(*)"], [[n]])
    return db


def _kwargs(queryname: str = "mytable", n: str = "0", mcl: str = "ROW_COUNT_GT(mytable, 0)") -> dict[str, Any]:
    return {"queryname": queryname, "n": n, "metacommandline": mcl}


# ---------------------------------------------------------------------------
# Unit tests: _parse_row_count_n
# ---------------------------------------------------------------------------


class TestParseRowCountN:
    """_parse_row_count_n parses integer strings and rejects non-integers."""

    def test_parses_zero(self) -> None:
        assert _parse_row_count_n("0", "ROW_COUNT_GT(t, 0)") == 0

    def test_parses_positive_integer(self) -> None:
        assert _parse_row_count_n("1000", "ROW_COUNT_GT(t, 1000)") == 1000

    def test_parses_with_whitespace(self) -> None:
        assert _parse_row_count_n("  42  ", "ROW_COUNT_GTE(t, 42)") == 42

    def test_raises_on_float_string(self) -> None:
        with pytest.raises(ErrInfo):
            _parse_row_count_n("3.14", "ROW_COUNT_EQ(t, 3.14)")

    def test_raises_on_non_numeric(self) -> None:
        with pytest.raises(ErrInfo):
            _parse_row_count_n("abc", "ROW_COUNT_LT(t, abc)")

    def test_raises_on_empty_string(self) -> None:
        with pytest.raises(ErrInfo):
            _parse_row_count_n("", "ROW_COUNT_GT(t, )")


# ---------------------------------------------------------------------------
# Unit tests: _row_count
# ---------------------------------------------------------------------------


class TestRowCountHelper:
    """_row_count queries the current DB and returns an integer."""

    def test_returns_integer_count(self) -> None:
        db = _mock_db_with_count(7)
        with patch.object(_state, "dbs") as mock_dbs:
            mock_dbs.current.return_value = db
            result = _row_count("mytable", "select count(*) from mytable;", "ROW_COUNT_GT(mytable, 0)")
        assert result == 7

    def test_re_raises_errinfo_from_db(self) -> None:
        db = MagicMock()
        db.select_data.side_effect = ErrInfo(type="db", other_msg="table not found")
        with patch.object(_state, "dbs") as mock_dbs:
            mock_dbs.current.return_value = db
            with pytest.raises(ErrInfo):
                _row_count("no_such_table", "select count(*) from no_such_table;", "ROW_COUNT_GT(no_such_table, 0)")

    def test_wraps_generic_exception_as_errinfo(self) -> None:
        db = MagicMock()
        db.select_data.side_effect = RuntimeError("connection dropped")
        with patch.object(_state, "dbs") as mock_dbs:
            mock_dbs.current.return_value = db
            with pytest.raises(ErrInfo):
                _row_count("t", "select count(*) from t;", "ROW_COUNT_GT(t, 0)")


# ---------------------------------------------------------------------------
# Unit tests: xf_row_count_gt
# ---------------------------------------------------------------------------


class TestXfRowCountGt:
    """ROW_COUNT_GT: true when count > N."""

    def test_true_when_count_exceeds_n(self) -> None:
        with patch.object(_state, "dbs") as mock_dbs:
            mock_dbs.current.return_value = _mock_db_with_count(5)
            assert xf_row_count_gt(**_kwargs(n="3")) is True

    def test_false_when_count_equals_n(self) -> None:
        with patch.object(_state, "dbs") as mock_dbs:
            mock_dbs.current.return_value = _mock_db_with_count(3)
            assert xf_row_count_gt(**_kwargs(n="3")) is False

    def test_false_when_count_below_n(self) -> None:
        with patch.object(_state, "dbs") as mock_dbs:
            mock_dbs.current.return_value = _mock_db_with_count(0)
            assert xf_row_count_gt(**_kwargs(n="1")) is False

    def test_true_gt_zero_when_one_row(self) -> None:
        with patch.object(_state, "dbs") as mock_dbs:
            mock_dbs.current.return_value = _mock_db_with_count(1)
            assert xf_row_count_gt(**_kwargs(n="0")) is True


# ---------------------------------------------------------------------------
# Unit tests: xf_row_count_gte
# ---------------------------------------------------------------------------


class TestXfRowCountGte:
    """ROW_COUNT_GTE: true when count >= N."""

    def test_true_when_count_exceeds_n(self) -> None:
        with patch.object(_state, "dbs") as mock_dbs:
            mock_dbs.current.return_value = _mock_db_with_count(10)
            assert xf_row_count_gte(**_kwargs(n="5", mcl="ROW_COUNT_GTE(mytable, 5)")) is True

    def test_true_when_count_equals_n(self) -> None:
        with patch.object(_state, "dbs") as mock_dbs:
            mock_dbs.current.return_value = _mock_db_with_count(5)
            assert xf_row_count_gte(**_kwargs(n="5", mcl="ROW_COUNT_GTE(mytable, 5)")) is True

    def test_false_when_count_below_n(self) -> None:
        with patch.object(_state, "dbs") as mock_dbs:
            mock_dbs.current.return_value = _mock_db_with_count(4)
            assert xf_row_count_gte(**_kwargs(n="5", mcl="ROW_COUNT_GTE(mytable, 5)")) is False


# ---------------------------------------------------------------------------
# Unit tests: xf_row_count_eq
# ---------------------------------------------------------------------------


class TestXfRowCountEq:
    """ROW_COUNT_EQ: true when count == N exactly."""

    def test_true_when_count_matches(self) -> None:
        with patch.object(_state, "dbs") as mock_dbs:
            mock_dbs.current.return_value = _mock_db_with_count(7)
            assert xf_row_count_eq(**_kwargs(n="7", mcl="ROW_COUNT_EQ(mytable, 7)")) is True

    def test_false_when_count_greater(self) -> None:
        with patch.object(_state, "dbs") as mock_dbs:
            mock_dbs.current.return_value = _mock_db_with_count(8)
            assert xf_row_count_eq(**_kwargs(n="7", mcl="ROW_COUNT_EQ(mytable, 7)")) is False

    def test_false_when_count_less(self) -> None:
        with patch.object(_state, "dbs") as mock_dbs:
            mock_dbs.current.return_value = _mock_db_with_count(6)
            assert xf_row_count_eq(**_kwargs(n="7", mcl="ROW_COUNT_EQ(mytable, 7)")) is False

    def test_true_zero_rows_eq_zero(self) -> None:
        with patch.object(_state, "dbs") as mock_dbs:
            mock_dbs.current.return_value = _mock_db_with_count(0)
            assert xf_row_count_eq(**_kwargs(n="0", mcl="ROW_COUNT_EQ(mytable, 0)")) is True


# ---------------------------------------------------------------------------
# Unit tests: xf_row_count_lt
# ---------------------------------------------------------------------------


class TestXfRowCountLt:
    """ROW_COUNT_LT: true when count < N."""

    def test_true_when_count_below_n(self) -> None:
        with patch.object(_state, "dbs") as mock_dbs:
            mock_dbs.current.return_value = _mock_db_with_count(2)
            assert xf_row_count_lt(**_kwargs(n="5", mcl="ROW_COUNT_LT(mytable, 5)")) is True

    def test_false_when_count_equals_n(self) -> None:
        with patch.object(_state, "dbs") as mock_dbs:
            mock_dbs.current.return_value = _mock_db_with_count(5)
            assert xf_row_count_lt(**_kwargs(n="5", mcl="ROW_COUNT_LT(mytable, 5)")) is False

    def test_false_when_count_exceeds_n(self) -> None:
        with patch.object(_state, "dbs") as mock_dbs:
            mock_dbs.current.return_value = _mock_db_with_count(9)
            assert xf_row_count_lt(**_kwargs(n="5", mcl="ROW_COUNT_LT(mytable, 5)")) is False


# ---------------------------------------------------------------------------
# Dispatch regex tests
# ---------------------------------------------------------------------------


class TestRowCountDispatchRegex:
    """The ROW_COUNT_* entries in the CONDITIONAL_TABLE match expected syntax."""

    @pytest.fixture(autouse=True)
    def _load_table(self) -> None:
        from execsql.metacommands.conditions import CONDITIONAL_TABLE

        self.ct = CONDITIONAL_TABLE

    def _match(self, keyword: str, line: str) -> dict | None:
        """Return groupdict if any entry with *keyword* in description matches *line*."""
        import re

        for mc in self.ct:
            if not mc.description or keyword not in mc.description:
                continue
            m = re.match(mc.rx.pattern, line.strip(), re.IGNORECASE)
            if m:
                return m.groupdict()
        return None

    def test_row_count_gt_unquoted_table(self) -> None:
        gd = self._match("ROW_COUNT_GT", "ROW_COUNT_GT(orders, 0)")
        assert gd is not None
        assert gd["queryname"] == "orders"
        assert gd["n"] == "0"

    def test_row_count_gte_with_spaces(self) -> None:
        gd = self._match("ROW_COUNT_GTE", "ROW_COUNT_GTE( staging , 1000 )")
        assert gd is not None
        assert gd["queryname"] == "staging"
        assert gd["n"] == "1000"

    def test_row_count_eq_zero(self) -> None:
        gd = self._match("ROW_COUNT_EQ", "ROW_COUNT_EQ(temp_results, 0)")
        assert gd is not None
        assert gd["queryname"] == "temp_results"
        assert gd["n"] == "0"

    def test_row_count_lt_large_n(self) -> None:
        gd = self._match("ROW_COUNT_LT", "ROW_COUNT_LT(audit_log, 999999)")
        assert gd is not None
        assert gd["n"] == "999999"

    def test_row_count_gt_dotted_schema_table(self) -> None:
        gd = self._match("ROW_COUNT_GT", "ROW_COUNT_GT(public.orders, 0)")
        assert gd is not None
        assert "public.orders" in gd["queryname"]

    def test_row_count_unrecognized_syntax_returns_none(self) -> None:
        # Non-integer threshold should not match the integer-only regex.
        gd = self._match("ROW_COUNT_GT", "ROW_COUNT_GT(orders, abc)")
        assert gd is None


# ---------------------------------------------------------------------------
# State reset helper (mirrors test_metacommands.py pattern)
# ---------------------------------------------------------------------------


def _flush_filewriter() -> None:
    import queue as _queue
    import time

    try:
        if _state.filewriter is None or not _state.filewriter.is_alive():
            return
        _state.filewriter.join(timeout=0.3)
        if not _state.filewriter.is_alive():
            return
        from execsql.utils.fileio import FileWriter, fw_input, fw_output

        token = ("_flush", time.monotonic())
        fw_input.put((FileWriter.CMD_CLOSE_ALL_AFTER_WRITE, ()))
        fw_input.put((FileWriter.CMD_PING, (token,)))
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


@pytest.fixture(autouse=True)
def _reset_execsql_state():
    yield
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
    if _state.dbs is not None:
        try:
            _state.dbs.closeall()
        except Exception:
            pass
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
    _state.gui_manager_queue = None
    _state.gui_manager_thread = None
    _state.gui_console = None
    import execsql.utils.gui as _gui_mod

    _gui_mod._active_backend = None


def qdb(db_path: Path, sql: str) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


@pytest.fixture
def script_runner(tmp_path: Path):
    db_path = tmp_path / "test.db"
    script_file = tmp_path / "test.sql"

    def run(script: str, *, new_db: bool = True):
        script_file.write_text(textwrap.dedent(script).strip(), encoding="utf-8")
        args = [str(script_file), str(db_path), "-t", "l"]
        if new_db:
            args.append("-n")
        result = _runner.invoke(app, args, catch_exceptions=False)
        _flush_filewriter()
        return result, db_path

    return run


# ---------------------------------------------------------------------------
# Integration tests via SQLite script runner
# ---------------------------------------------------------------------------


class TestRowCountIntegration:
    """End-to-end integration tests using SQLite and a real script runner."""

    def test_row_count_gt_true_branch_executes(self, script_runner) -> None:
        """ROW_COUNT_GT triggers the true branch when rows > N."""
        result, db = script_runner("""
            create table src (x integer);
            insert into src values (1);
            insert into src values (2);
            create table result (val text);
            -- !x! IF (ROW_COUNT_GT(src, 0))
            insert into result values ('yes');
            -- !x! ELSE
            insert into result values ('no');
            -- !x! ENDIF
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT val FROM result") == [("yes",)]

    def test_row_count_gt_false_branch_executes(self, script_runner) -> None:
        """ROW_COUNT_GT triggers the false branch when rows <= N."""
        result, db = script_runner("""
            create table src (x integer);
            create table result (val text);
            -- !x! IF (ROW_COUNT_GT(src, 0))
            insert into result values ('yes');
            -- !x! ELSE
            insert into result values ('no');
            -- !x! ENDIF
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT val FROM result") == [("no",)]

    def test_row_count_gte_exact_match(self, script_runner) -> None:
        """ROW_COUNT_GTE is true when count equals N exactly."""
        result, db = script_runner("""
            create table src (x integer);
            insert into src values (1);
            insert into src values (2);
            insert into src values (3);
            create table result (val text);
            -- !x! IF (ROW_COUNT_GTE(src, 3))
            insert into result values ('yes');
            -- !x! ELSE
            insert into result values ('no');
            -- !x! ENDIF
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT val FROM result") == [("yes",)]

    def test_row_count_eq_correct_count(self, script_runner) -> None:
        """ROW_COUNT_EQ is true when count matches exactly."""
        result, db = script_runner("""
            create table src (x integer);
            insert into src values (10);
            insert into src values (20);
            create table result (val text);
            -- !x! IF (ROW_COUNT_EQ(src, 2))
            insert into result values ('yes');
            -- !x! ELSE
            insert into result values ('no');
            -- !x! ENDIF
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT val FROM result") == [("yes",)]

    def test_row_count_eq_wrong_count(self, script_runner) -> None:
        """ROW_COUNT_EQ is false when count does not match."""
        result, db = script_runner("""
            create table src (x integer);
            insert into src values (10);
            create table result (val text);
            -- !x! IF (ROW_COUNT_EQ(src, 5))
            insert into result values ('yes');
            -- !x! ELSE
            insert into result values ('no');
            -- !x! ENDIF
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT val FROM result") == [("no",)]

    def test_row_count_lt_empty_table(self, script_runner) -> None:
        """ROW_COUNT_LT is true for an empty table when N > 0."""
        result, db = script_runner("""
            create table src (x integer);
            create table result (val text);
            -- !x! IF (ROW_COUNT_LT(src, 1))
            insert into result values ('yes');
            -- !x! ELSE
            insert into result values ('no');
            -- !x! ENDIF
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT val FROM result") == [("yes",)]

    def test_assert_row_count_gt_passes(self, script_runner) -> None:
        """ASSERT ROW_COUNT_GT passes when table has rows."""
        result, db = script_runner("""
            create table src (x integer);
            insert into src values (42);
            -- !x! ASSERT ROW_COUNT_GT(src, 0) "src must not be empty"
            create table result (val text);
            insert into result values ('ok');
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT val FROM result") == [("ok",)]

    def test_assert_row_count_gte_fails_halts_script(self, script_runner) -> None:
        """ASSERT ROW_COUNT_GTE fails and halts when condition is false."""
        result, _db = script_runner("""
            create table src (x integer);
            -- !x! ASSERT ROW_COUNT_GTE(src, 5) "need 5 rows"
            create table should_not_exist (val text);
        """)
        # Script should exit non-zero due to assertion failure.
        assert result.exit_code != 0
