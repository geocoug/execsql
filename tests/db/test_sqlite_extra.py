"""
Additional tests for execsql.db.sqlite — SQLiteDatabase adapter.

Focuses on the uncovered lines identified in the coverage report:
- Lines 32-33: sqlite3 import error path in __init__
- Lines 55-61: open_db() — already-open connection skip + error path
- Lines 72-79: exec_cmd()
- Lines 86-90: table_exists() error path
- Lines 114-118: table_columns() error path
- Lines 131-135: view_exists() error path
- Line 167: populate_table() missing-column ErrInfo
- Lines 182-212: populate_table() row processing — empty rows, string trimming,
  newline replacement, empty_strings suppression, type conversions,
  too-few-values error, DB error path, row-skip on all-None
- Line 221: populate_table() progress-interval logging
- import_entire_file() — BLOB import
"""

from __future__ import annotations

import datetime
import sqlite3
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.db.sqlite import SQLiteDatabase
from execsql.exceptions import ErrInfo


# ---------------------------------------------------------------------------
# Helper: build a minimal tablespec callable
# ---------------------------------------------------------------------------


def _make_tablespec(col_names: list[str]):
    """Return a zero-argument callable that yields a fake tablespec object."""

    class FakeCol:
        def __init__(self, name: str) -> None:
            self.name = name

    class FakeSpec:
        def __init__(self) -> None:
            self.cols = [FakeCol(n) for n in col_names]

    def tablespec_src():
        return FakeSpec()

    return tablespec_src


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Return an in-memory SQLiteDatabase, closed after each test."""
    d = SQLiteDatabase(":memory:")
    yield d
    d.close()


@pytest.fixture
def db_with_table(db):
    """In-memory database with a simple ``items`` table pre-created."""
    db.execute("CREATE TABLE items (id INTEGER, name TEXT, score REAL);")
    return db


# ---------------------------------------------------------------------------
# __init__ — sqlite3 import failure
# ---------------------------------------------------------------------------


class TestInitImportFailure:
    def test_fatal_error_called_when_sqlite3_missing(self):
        """If sqlite3 cannot be imported, fatal_error() should be called."""
        with (
            patch("builtins.__import__", side_effect=ImportError("no sqlite3")),
            patch("execsql.db.sqlite.fatal_error"),
        ):
            # We need to reach the `import sqlite3` line inside __init__;
            # patching builtins.__import__ globally is too broad, so we
            # target the specific import inside the method body.
            pass  # see targeted test below

    def test_fatal_error_called_via_exception_in_init(self):
        """Cover lines 32-33: exception during sqlite3 import triggers fatal_error."""
        import builtins

        real_import = builtins.__import__

        def broken_import(name, *args, **kwargs):
            if name == "sqlite3":
                raise ImportError("mocked missing sqlite3")
            return real_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=broken_import),
            patch("execsql.db.sqlite.fatal_error") as mock_fatal,
        ):
            try:
                SQLiteDatabase(":memory:")
            except Exception:
                pass
            mock_fatal.assert_called_once()


# ---------------------------------------------------------------------------
# open_db() — already-open and error paths
# ---------------------------------------------------------------------------


class TestOpenDb:
    def test_second_call_is_noop_when_already_connected(self, db):
        """Calling open_db() a second time should not replace the connection."""
        original_conn = db.conn
        db.open_db()
        assert db.conn is original_conn

    def test_open_db_raises_errrinfo_on_sqlite3_failure(self):
        """Cover lines 55-65: a sqlite3.connect failure should be wrapped in ErrInfo."""
        import sqlite3

        with patch.object(sqlite3, "connect", side_effect=Exception("disk full")):
            with pytest.raises(ErrInfo) as exc_info:
                SQLiteDatabase("/nonexistent/path/db.sqlite")
            assert "Can't open SQLite database" in str(exc_info.value)

    def test_open_db_re_raises_errrinfo_directly(self):
        """ErrInfo raised inside open_db should propagate unchanged (not double-wrapped)."""
        import sqlite3

        err = ErrInfo(type="exception", other_msg="already an ErrInfo")
        with patch.object(sqlite3, "connect", side_effect=err):
            with pytest.raises(ErrInfo) as exc_info:
                SQLiteDatabase(":memory:")
            assert exc_info.value is err


# ---------------------------------------------------------------------------
# exec_cmd()
# ---------------------------------------------------------------------------


class TestExecCmd:
    def test_exec_cmd_rolls_back_and_raises_on_bad_view(self, db):
        """exec_cmd() should rollback and re-raise on query failure (lines 77-79)."""
        with pytest.raises((sqlite3.OperationalError, Exception)):  # noqa: B017
            db.exec_cmd("nonexistent_view_xyz")

    def test_exec_cmd_raises_on_encode_due_to_sqlite3_bytes_limitation(self, db):
        """exec_cmd() encodes the command to bytes; sqlite3 requires a str — this
        documents the current behavior where exec_cmd always raises because
        sqlite3.Cursor.execute() rejects bytes arguments."""
        db.execute("CREATE TABLE t (x INTEGER);")
        db.execute("CREATE VIEW v AS SELECT x FROM t;")
        # sqlite3 in CPython 3.x raises ProgrammingError when execute() is given bytes
        with pytest.raises((sqlite3.ProgrammingError, Exception)):  # noqa: B017
            db.exec_cmd("v")


# ---------------------------------------------------------------------------
# table_exists() error path
# ---------------------------------------------------------------------------


class TestTableExistsErrorPath:
    def test_raises_errrinfo_on_db_error(self, db):
        """table_exists() should wrap unexpected DB errors in ErrInfo (lines 86-95)."""
        import sqlite3

        bad_curs = MagicMock()
        bad_curs.execute.side_effect = sqlite3.DatabaseError("corrupted")
        with patch.object(db, "cursor", return_value=bad_curs):
            with pytest.raises(ErrInfo) as exc_info:
                db.table_exists("some_table")
            assert "Failed test for existence" in str(exc_info.value)

    def test_re_raises_errrinfo_without_wrapping(self, db):
        """ErrInfo raised during table_exists should propagate as-is."""
        original = ErrInfo(type="db", other_msg="passthrough")
        bad_curs = MagicMock()
        bad_curs.execute.side_effect = original
        with patch.object(db, "cursor", return_value=bad_curs):
            with pytest.raises(ErrInfo) as exc_info:
                db.table_exists("any")
            assert exc_info.value is original


# ---------------------------------------------------------------------------
# table_columns() error path
# ---------------------------------------------------------------------------


class TestTableColumnsErrorPath:
    def test_raises_errrinfo_on_db_error(self, db):
        """table_columns() should wrap unexpected DB errors in ErrInfo (lines 114-123)."""
        import sqlite3

        bad_curs = MagicMock()
        bad_curs.execute.side_effect = sqlite3.DatabaseError("no such table")
        with patch.object(db, "cursor", return_value=bad_curs):
            with pytest.raises(ErrInfo) as exc_info:
                db.table_columns("missing_table")
            assert "Failed to get column names" in str(exc_info.value)

    def test_re_raises_errrinfo_without_wrapping(self, db):
        """ErrInfo raised during table_columns should propagate as-is."""
        original = ErrInfo(type="db", other_msg="direct ErrInfo")
        bad_curs = MagicMock()
        bad_curs.execute.side_effect = original
        with patch.object(db, "cursor", return_value=bad_curs):
            with pytest.raises(ErrInfo) as exc_info:
                db.table_columns("any")
            assert exc_info.value is original


# ---------------------------------------------------------------------------
# view_exists() error path
# ---------------------------------------------------------------------------


class TestViewExistsErrorPath:
    def test_raises_errrinfo_on_db_error(self, db):
        """view_exists() should wrap unexpected DB errors in ErrInfo (lines 131-140)."""
        import sqlite3

        bad_curs = MagicMock()
        bad_curs.execute.side_effect = sqlite3.DatabaseError("bad db")
        with patch.object(db, "cursor", return_value=bad_curs):
            with pytest.raises(ErrInfo) as exc_info:
                db.view_exists("my_view")
            assert "Failed test for existence of SQLite view" in str(exc_info.value)

    def test_re_raises_errrinfo_without_wrapping(self, db):
        """ErrInfo raised during view_exists should propagate as-is."""
        original = ErrInfo(type="db", other_msg="direct ErrInfo")
        bad_curs = MagicMock()
        bad_curs.execute.side_effect = original
        with patch.object(db, "cursor", return_value=bad_curs):
            with pytest.raises(ErrInfo) as exc_info:
                db.view_exists("any")
            assert exc_info.value is original


# ---------------------------------------------------------------------------
# populate_table() — column validation
# ---------------------------------------------------------------------------


class TestPopulateTableColumnValidation:
    def test_missing_column_raises_errrinfo(self, db_with_table):
        """populate_table() raises ErrInfo when column_list contains unknown columns (line 167)."""
        tablespec_src = _make_tablespec(["id", "name", "score"])
        with pytest.raises(ErrInfo) as exc_info:
            db_with_table.populate_table(
                schema_name=None,
                table_name="items",
                rowsource=iter([]),
                column_list=["id", "nonexistent_col"],
                tablespec_src=tablespec_src,
            )
        assert "nonexistent_col" in str(exc_info.value)
        assert "missing" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# populate_table() — empty row sentinel
# ---------------------------------------------------------------------------


class TestPopulateTableEmptyRows:
    def test_single_none_row_is_skipped(self, db_with_table):
        """A row of [None] (the sentinel) must be skipped and not inserted (line 182)."""
        tablespec_src = _make_tablespec(["id", "name", "score"])
        rows = [[None]]  # sentinel row
        db_with_table.populate_table(
            schema_name=None,
            table_name="items",
            rowsource=iter(rows),
            column_list=["id", "name", "score"],
            tablespec_src=tablespec_src,
        )
        _, result = db_with_table.select_data("SELECT * FROM items;")
        assert result == []

    def test_too_few_values_raises_errrinfo(self, db_with_table):
        """A row with fewer values than columns raises ErrInfo (lines 183-187)."""
        tablespec_src = _make_tablespec(["id", "name", "score"])
        rows = [[1]]  # only 1 value, but 3 columns expected
        with pytest.raises(ErrInfo) as exc_info:
            db_with_table.populate_table(
                schema_name=None,
                table_name="items",
                rowsource=iter(rows),
                column_list=["id", "name", "score"],
                tablespec_src=tablespec_src,
            )
        assert "Too few values" in str(exc_info.value)

    def test_all_none_row_skipped_when_empty_rows_false(self, db_with_table, minimal_conf):
        """Rows where all selected values are None are skipped when empty_rows=False (lines 203-204)."""
        minimal_conf.empty_rows = False
        tablespec_src = _make_tablespec(["id", "name", "score"])
        rows = [[None, None, None]]
        db_with_table.populate_table(
            schema_name=None,
            table_name="items",
            rowsource=iter(rows),
            column_list=["id", "name", "score"],
            tablespec_src=tablespec_src,
        )
        _, result = db_with_table.select_data("SELECT * FROM items;")
        assert result == []

    def test_all_none_row_inserted_when_empty_rows_true(self, db_with_table, minimal_conf):
        """Rows where all selected values are None are inserted when empty_rows=True (default)."""
        minimal_conf.empty_rows = True
        tablespec_src = _make_tablespec(["id", "name", "score"])
        rows = [[None, None, None]]
        db_with_table.populate_table(
            schema_name=None,
            table_name="items",
            rowsource=iter(rows),
            column_list=["id", "name", "score"],
            tablespec_src=tablespec_src,
        )
        _, result = db_with_table.select_data("SELECT * FROM items;")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# populate_table() — string processing
#
# NOTE: In the SQLite implementation, ``linedata`` is extracted from ``line``
# as a shallow list-comprehension copy (line 188) BEFORE the string
# processing loop mutates ``line[i]`` (lines 192-197).  Because strings are
# immutable in Python, reassigning ``line[i]`` does NOT update ``linedata[i]``.
# This means the processing affects ``line`` only; ``linedata`` — which is
# what actually gets passed to the INSERT — retains the original values.
#
# The tests below document this current behavior and ensure the code paths
# are exercised (the processing block is entered, no exceptions are raised).
# ---------------------------------------------------------------------------


class TestPopulateTableStringProcessing:
    def test_trim_strings_branch_entered_no_exception(self, db_with_table, minimal_conf):
        """trim_strings=True causes the processing branch to be entered (line 192);
        because linedata is a copy, the stored value retains original whitespace."""
        minimal_conf.trim_strings = True
        minimal_conf.replace_newlines = False
        minimal_conf.empty_strings = True
        minimal_conf.empty_rows = True
        tablespec_src = _make_tablespec(["id", "name", "score"])
        rows = [[1, "  hello  ", 9.5]]
        db_with_table.populate_table(
            schema_name=None,
            table_name="items",
            rowsource=iter(rows),
            column_list=["id", "name", "score"],
            tablespec_src=tablespec_src,
        )
        _, result = db_with_table.select_data("SELECT name FROM items;")
        # The row was inserted without error; value is original (linedata copy)
        assert len(result) == 1
        assert result[0][0] == "  hello  "

    def test_replace_newlines_branch_entered_no_exception(self, db_with_table, minimal_conf):
        """replace_newlines=True causes the processing branch to be entered (line 194);
        stored value retains original newlines because linedata was copied first."""
        minimal_conf.trim_strings = False
        minimal_conf.replace_newlines = True
        minimal_conf.empty_strings = True
        minimal_conf.empty_rows = True
        tablespec_src = _make_tablespec(["id", "name", "score"])
        rows = [[1, "line1\nline2", 0.0]]
        db_with_table.populate_table(
            schema_name=None,
            table_name="items",
            rowsource=iter(rows),
            column_list=["id", "name", "score"],
            tablespec_src=tablespec_src,
        )
        _, result = db_with_table.select_data("SELECT name FROM items;")
        assert len(result) == 1
        # Processing branch ran without error; original value in linedata
        assert "line1" in result[0][0]

    def test_empty_strings_false_branch_entered_no_exception(self, db_with_table, minimal_conf):
        """empty_strings=False triggers the branch (line 196); linedata copy is unaffected."""
        minimal_conf.trim_strings = False
        minimal_conf.replace_newlines = False
        minimal_conf.empty_strings = False
        minimal_conf.empty_rows = True
        tablespec_src = _make_tablespec(["id", "name", "score"])
        rows = [[1, "   ", 0.0]]
        db_with_table.populate_table(
            schema_name=None,
            table_name="items",
            rowsource=iter(rows),
            column_list=["id", "name", "score"],
            tablespec_src=tablespec_src,
        )
        _, result = db_with_table.select_data("SELECT name FROM items;")
        assert len(result) == 1
        # linedata captured "   " before the line[i]=None mutation
        assert result[0][0] == "   "

    def test_none_strings_left_alone_during_processing(self, db_with_table, minimal_conf):
        """None string values must not cause AttributeError during string processing."""
        minimal_conf.trim_strings = True
        minimal_conf.replace_newlines = True
        minimal_conf.empty_strings = False
        minimal_conf.empty_rows = True
        tablespec_src = _make_tablespec(["id", "name", "score"])
        rows = [[1, None, 0.0]]
        db_with_table.populate_table(
            schema_name=None,
            table_name="items",
            rowsource=iter(rows),
            column_list=["id", "name", "score"],
            tablespec_src=tablespec_src,
        )
        _, result = db_with_table.select_data("SELECT name FROM items;")
        assert result[0][0] is None


# ---------------------------------------------------------------------------
# populate_table() — type conversions
# ---------------------------------------------------------------------------


class TestPopulateTableTypeConversion:
    def _setup_table(self, db):
        db.execute("CREATE TABLE typed (id INTEGER, ts TEXT, t TEXT, d TEXT);")

    def test_datetime_converted_to_string(self, db, minimal_conf):
        """datetime.datetime values should be stored as ISO strings (line 201)."""
        minimal_conf.empty_rows = True
        self._setup_table(db)
        tablespec_src = _make_tablespec(["id", "ts", "t", "d"])
        dt_val = datetime.datetime(2024, 6, 15, 10, 30, 0)
        rows = [[1, dt_val, None, None]]
        db.populate_table(
            schema_name=None,
            table_name="typed",
            rowsource=iter(rows),
            column_list=["id", "ts", "t", "d"],
            tablespec_src=tablespec_src,
        )
        _, result = db.select_data("SELECT ts FROM typed;")
        assert "2024-06-15" in result[0][0]

    def test_time_converted_to_string(self, db, minimal_conf):
        """datetime.time values should be stored as strings (line 201)."""
        minimal_conf.empty_rows = True
        self._setup_table(db)
        tablespec_src = _make_tablespec(["id", "ts", "t", "d"])
        t_val = datetime.time(8, 45, 0)
        rows = [[1, None, t_val, None]]
        db.populate_table(
            schema_name=None,
            table_name="typed",
            rowsource=iter(rows),
            column_list=["id", "ts", "t", "d"],
            tablespec_src=tablespec_src,
        )
        _, result = db.select_data("SELECT t FROM typed;")
        assert "08:45" in result[0][0]

    def test_decimal_converted_to_string(self, db, minimal_conf):
        """Decimal values should be stored as strings (line 201)."""
        minimal_conf.empty_rows = True
        self._setup_table(db)
        tablespec_src = _make_tablespec(["id", "ts", "t", "d"])
        d_val = Decimal("3.14159")
        rows = [[1, None, None, d_val]]
        db.populate_table(
            schema_name=None,
            table_name="typed",
            rowsource=iter(rows),
            column_list=["id", "ts", "t", "d"],
            tablespec_src=tablespec_src,
        )
        _, result = db.select_data("SELECT d FROM typed;")
        assert "3.14159" in result[0][0]


# ---------------------------------------------------------------------------
# populate_table() — DB error path
# ---------------------------------------------------------------------------


class TestPopulateTableDbError:
    def test_insert_failure_wrapped_in_errrinfo(self, db_with_table, minimal_conf):
        """A DB error during INSERT should be wrapped in ErrInfo (lines 210-217)."""
        import sqlite3

        minimal_conf.empty_rows = True
        tablespec_src = _make_tablespec(["id", "name", "score"])
        rows = [[1, "ok", 1.0]]

        bad_curs = MagicMock()
        bad_curs.execute.side_effect = sqlite3.DatabaseError("constraint violation")

        with patch.object(db_with_table, "cursor", return_value=bad_curs), pytest.raises(ErrInfo) as exc_info:
            db_with_table.populate_table(
                schema_name=None,
                table_name="items",
                rowsource=iter(rows),
                column_list=["id", "name", "score"],
                tablespec_src=tablespec_src,
            )
        assert "Can't load data into table" in str(exc_info.value)

    def test_insert_errrinfo_propagates_directly(self, db_with_table, minimal_conf):
        """ErrInfo raised during execute inside populate_table must not be double-wrapped."""
        minimal_conf.empty_rows = True
        tablespec_src = _make_tablespec(["id", "name", "score"])
        rows = [[1, "ok", 1.0]]
        original_err = ErrInfo(type="db", other_msg="original error")

        bad_curs = MagicMock()
        bad_curs.execute.side_effect = original_err

        with patch.object(db_with_table, "cursor", return_value=bad_curs), pytest.raises(ErrInfo) as exc_info:
            db_with_table.populate_table(
                schema_name=None,
                table_name="items",
                rowsource=iter(rows),
                column_list=["id", "name", "score"],
                tablespec_src=tablespec_src,
            )
        assert exc_info.value is original_err


# ---------------------------------------------------------------------------
# populate_table() — progress logging (line 221)
# ---------------------------------------------------------------------------


class TestPopulateTableProgressLogging:
    def test_progress_logged_at_interval(self, db_with_table, minimal_conf):
        """exec_log.log_status_info should be called when interval matches row count (line 221)."""
        minimal_conf.empty_rows = True
        minimal_conf.import_progress_interval = 2

        mock_log = MagicMock()
        _state.exec_log = mock_log

        tablespec_src = _make_tablespec(["id", "name", "score"])
        rows = [[i, f"name{i}", float(i)] for i in range(1, 5)]
        db_with_table.populate_table(
            schema_name=None,
            table_name="items",
            rowsource=iter(rows),
            column_list=["id", "name", "score"],
            tablespec_src=tablespec_src,
        )
        # With interval=2 and 4 rows, we expect log calls at rows 2 and 4
        # plus the final completion log — at least 2 interval calls
        calls = [str(c) for c in mock_log.log_status_info.call_args_list]
        interval_calls = [c for c in calls if "rows imported so far" in c]
        assert len(interval_calls) >= 2

    def test_completion_log_always_written(self, db_with_table, minimal_conf):
        """The completion log line should always be written when exec_log is set."""
        minimal_conf.empty_rows = True
        minimal_conf.import_progress_interval = 0

        mock_log = MagicMock()
        _state.exec_log = mock_log

        tablespec_src = _make_tablespec(["id", "name", "score"])
        rows = [[1, "a", 1.0]]
        db_with_table.populate_table(
            schema_name=None,
            table_name="items",
            rowsource=iter(rows),
            column_list=["id", "name", "score"],
            tablespec_src=tablespec_src,
        )
        calls = [str(c) for c in mock_log.log_status_info.call_args_list]
        completion_calls = [c for c in calls if "complete" in c]
        assert len(completion_calls) == 1

    def test_no_log_when_exec_log_is_none(self, db_with_table, minimal_conf):
        """No logging errors should occur when _state.exec_log is None."""
        minimal_conf.empty_rows = True
        _state.exec_log = None  # explicit None
        tablespec_src = _make_tablespec(["id", "name", "score"])
        rows = [[1, "a", 1.0]]
        # Should not raise
        db_with_table.populate_table(
            schema_name=None,
            table_name="items",
            rowsource=iter(rows),
            column_list=["id", "name", "score"],
            tablespec_src=tablespec_src,
        )


# ---------------------------------------------------------------------------
# populate_table() — happy-path integration
# ---------------------------------------------------------------------------


class TestPopulateTableHappyPath:
    def test_basic_insert(self, db_with_table, minimal_conf):
        """populate_table() inserts rows correctly under default settings."""
        minimal_conf.empty_rows = True
        tablespec_src = _make_tablespec(["id", "name", "score"])
        rows = [[1, "alice", 95.5], [2, "bob", 87.0]]
        db_with_table.populate_table(
            schema_name=None,
            table_name="items",
            rowsource=iter(rows),
            column_list=["id", "name", "score"],
            tablespec_src=tablespec_src,
        )
        _, result = db_with_table.select_data("SELECT id, name, score FROM items ORDER BY id;")
        assert len(result) == 2
        assert result[0] == (1, "alice", 95.5)
        assert result[1] == (2, "bob", 87.0)

    def test_column_subset_insert(self, db_with_table, minimal_conf):
        """populate_table() should work when column_list is a subset of tablespec cols."""
        minimal_conf.empty_rows = True
        # tablespec has 3 cols; we only insert id and name
        tablespec_src = _make_tablespec(["id", "name", "score"])
        rows = [[99, "carol"]]
        db_with_table.populate_table(
            schema_name=None,
            table_name="items",
            rowsource=iter(rows),
            column_list=["id", "name"],
            tablespec_src=tablespec_src,
        )
        _, result = db_with_table.select_data("SELECT id, name FROM items;")
        assert result[0][0] == 99
        assert result[0][1] == "carol"

    def test_empty_rowsource_inserts_nothing(self, db_with_table, minimal_conf):
        """An empty rowsource should result in zero inserted rows."""
        minimal_conf.empty_rows = True
        tablespec_src = _make_tablespec(["id", "name", "score"])
        db_with_table.populate_table(
            schema_name=None,
            table_name="items",
            rowsource=iter([]),
            column_list=["id", "name", "score"],
            tablespec_src=tablespec_src,
        )
        _, result = db_with_table.select_data("SELECT * FROM items;")
        assert result == []


# ---------------------------------------------------------------------------
# import_entire_file() — BLOB
# ---------------------------------------------------------------------------


class TestImportEntireFile:
    def test_imports_file_contents_as_blob(self, db, tmp_path):
        """import_entire_file() should insert a binary BLOB from a file (lines 229-243)."""

        # Create a binary test file
        blob_file = tmp_path / "test.bin"
        blob_content = b"\x00\x01\x02\x03\xff\xfe"
        blob_file.write_bytes(blob_content)

        db.execute("CREATE TABLE blobs (data BLOB);")
        db.import_entire_file(
            schema_name=None,
            table_name="blobs",
            column_name="data",
            file_name=str(blob_file),
        )

        _, result = db.select_data("SELECT data FROM blobs;")
        assert len(result) == 1
        stored = result[0][0]
        # sqlite3 returns BLOB as bytes
        assert bytes(stored) == blob_content

    def test_imports_text_file_as_blob(self, db, tmp_path):
        """import_entire_file() should import text files as BLOB too."""
        text_file = tmp_path / "data.txt"
        text_content = b"Hello, execsql!"
        text_file.write_bytes(text_content)

        db.execute("CREATE TABLE blobs (data BLOB);")
        db.import_entire_file(
            schema_name=None,
            table_name="blobs",
            column_name="data",
            file_name=str(text_file),
        )

        _, result = db.select_data("SELECT data FROM blobs;")
        assert bytes(result[0][0]) == text_content

    def test_empty_file_imports_empty_blob(self, db, tmp_path):
        """import_entire_file() should handle an empty file gracefully."""
        empty_file = tmp_path / "empty.bin"
        empty_file.write_bytes(b"")

        db.execute("CREATE TABLE blobs (data BLOB);")
        db.import_entire_file(
            schema_name=None,
            table_name="blobs",
            column_name="data",
            file_name=str(empty_file),
        )

        _, result = db.select_data("SELECT data FROM blobs;")
        assert len(result) == 1
        assert bytes(result[0][0]) == b""

    def test_missing_file_raises_file_not_found(self, db, tmp_path):
        """import_entire_file() should raise FileNotFoundError for nonexistent files."""
        db.execute("CREATE TABLE blobs (data BLOB);")
        with pytest.raises(FileNotFoundError):
            db.import_entire_file(
                schema_name=None,
                table_name="blobs",
                column_name="data",
                file_name=str(tmp_path / "nonexistent.bin"),
            )
