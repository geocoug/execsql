"""Tests for the custom exception hierarchy in execsql.exceptions."""

from __future__ import annotations

import pytest

from execsql.exceptions import (
    ColumnError,
    CondParserError,
    ConfigError,
    ConsoleUIError,
    DataTableError,
    DataTypeError,
    DatabaseNotImplementedError,
    DbTypeError,
    ErrInfo,
    ExecSqlTimeoutError,
    NumericParserError,
    OdsFileError,
    XlsFileError,
    XlsxFileError,
)


# ---------------------------------------------------------------------------
# ConfigError
# ---------------------------------------------------------------------------


class TestConfigError:
    def test_is_exception(self):
        e = ConfigError("bad value")
        assert isinstance(e, Exception)

    def test_value_stored(self):
        e = ConfigError("bad value")
        assert e.value == "bad value"

    def test_repr(self):
        assert "bad value" in repr(ConfigError("bad value"))


# ---------------------------------------------------------------------------
# ExecSqlTimeoutError
# ---------------------------------------------------------------------------


class TestExecSqlTimeoutError:
    def test_is_exception(self):
        assert isinstance(ExecSqlTimeoutError(), Exception)

    def test_does_not_shadow_builtin(self):
        # Must not be the same class as the Python built-in TimeoutError
        assert ExecSqlTimeoutError is not TimeoutError


# ---------------------------------------------------------------------------
# ErrInfo
# ---------------------------------------------------------------------------


class TestErrInfo:
    def test_basic_construction(self):
        e = ErrInfo(type="db")
        assert e.type == "db"
        assert e.command is None
        assert e.exception is None
        assert e.other is None

    def test_with_all_fields(self):
        e = ErrInfo(
            type="cmd",
            command_text="IMPORT ...",
            exception_msg="file not found",
            other_msg="extra info",
        )
        assert e.type == "cmd"
        assert e.command == "IMPORT ..."
        assert "file not found" in e.exception
        assert "extra info" in e.other

    @pytest.mark.parametrize(
        "err_type,expected_text",
        [
            ("db", "**** Error in SQL statement."),
            ("cmd", "**** Error in metacommand."),
            ("log", "**** Error in logging."),
            ("error", "**** General error."),
            ("systemexit", "**** Exit."),
            ("exception", "**** Exception."),
            ("unknown_t", "**** Error of unknown type: unknown_t"),
        ],
    )
    def test_eval_err_prefixes(self, err_type, expected_text):
        e = ErrInfo(type=err_type)
        msg = e.eval_err()
        assert msg.startswith(expected_text)

    def test_eval_err_includes_exception_msg(self):
        e = ErrInfo(type="db", exception_msg="column 'x' does not exist")
        msg = e.eval_err()
        assert "column 'x' does not exist" in msg

    def test_eval_err_includes_timestamp(self):
        e = ErrInfo(type="error")
        msg = e.eval_err()
        assert "UTC" in msg

    def test_script_info_with_location(self):
        e = ErrInfo(type="db")
        e.script_file = "my_script.sql"
        e.script_line_no = 42
        assert "42" in e.script_info()
        assert "my_script.sql" in e.script_info()

    def test_script_info_without_location(self):
        e = ErrInfo(type="db")
        assert e.script_info() is None

    def test_cmd_info_metacommand(self):
        e = ErrInfo(type="cmd")
        e.cmdtype = "cmd"
        e.cmd = "EXPORT mytable TO file.csv"
        info = e.cmd_info()
        assert "EXPORT mytable TO file.csv" in info

    def test_cmd_info_sql(self):
        e = ErrInfo(type="db")
        e.cmdtype = "sql"
        e.cmd = "SELECT 1"
        info = e.cmd_info()
        assert "SELECT 1" in info

    def test_cmd_info_not_set(self):
        e = ErrInfo(type="db")
        assert e.cmd_info() is None

    def test_errmsg_alias(self):
        e = ErrInfo(type="error")
        assert e.errmsg() == e.eval_err()

    def test_is_exception(self):
        e = ErrInfo(type="db")
        assert isinstance(e, Exception)

    def test_newlines_in_exception_msg_indented(self):
        e = ErrInfo(type="db", exception_msg="line1\nline2")
        # Newlines are replaced with "\n     " for readable indentation
        assert "\n     line2" in e.exception

    def test_repr(self):
        e = ErrInfo(type="db", command_text="SELECT 1")
        r = repr(e)
        assert "ErrInfo(" in r
        assert "db" in r

    def test_eval_err_includes_script_info(self):
        e = ErrInfo(type="db")
        e.script_file = "my_script.sql"
        e.script_line_no = 10
        msg = e.eval_err()
        assert "my_script.sql" in msg
        assert "10" in msg

    def test_eval_err_includes_other_msg(self):
        e = ErrInfo(type="error", other_msg="extra context")
        msg = e.eval_err()
        assert "extra context" in msg

    def test_eval_err_includes_command_text(self):
        e = ErrInfo(type="db", command_text="SELECT * FROM x")
        msg = e.eval_err()
        assert "SELECT * FROM x" in msg

    def test_eval_err_includes_cmd_info_when_set(self):
        e = ErrInfo(type="cmd")
        e.cmdtype = "cmd"
        e.cmd = "EXPORT t TO f.csv"
        msg = e.eval_err()
        assert "EXPORT t TO f.csv" in msg

    def test_write_outputs_to_stderr(self, capsys):
        e = ErrInfo(type="error", other_msg="something went wrong")
        errmsg = e.write()
        captured = capsys.readouterr()
        assert "something went wrong" in captured.err
        assert errmsg is not None


# ---------------------------------------------------------------------------
# DataTypeError
# ---------------------------------------------------------------------------


class TestDataTypeError:
    def test_str_format(self):
        e = DataTypeError("integer", "not an int")
        assert "integer" in str(e)
        assert "not an int" in str(e)

    def test_repr(self):
        e = DataTypeError("integer", "not an int")
        assert "integer" in repr(e)

    def test_defaults_when_none(self):
        e = DataTypeError(None, None)
        assert "Unspecified" in str(e)


# ---------------------------------------------------------------------------
# DbTypeError
# ---------------------------------------------------------------------------


class TestDbTypeError:
    def test_str_with_data_type(self):
        from execsql.types import DT_Integer

        dt = DT_Integer()
        e = DbTypeError("PostgreSQL", dt, "unsupported")
        assert "PostgreSQL" in str(e)
        assert "unsupported" in str(e)

    def test_str_without_data_type(self):
        e = DbTypeError("SQLite", None, "no type")
        assert "SQLite" in str(e)

    def test_repr(self):
        e = DbTypeError("MySQL", None, "oops")
        r = repr(e)
        assert "DbTypeError(" in r
        assert "MySQL" in r


# ---------------------------------------------------------------------------
# ColumnError / DataTableError
# ---------------------------------------------------------------------------


class TestColumnError:
    def test_basic(self):
        e = ColumnError("bad column")
        assert isinstance(e, Exception)

    def test_repr(self):
        assert "bad column" in repr(ColumnError("bad column"))

    def test_str(self):
        e = ColumnError("bad column")
        assert "bad column" in str(e)


class TestDataTableError:
    def test_basic(self):
        e = DataTableError("bad table")
        assert isinstance(e, Exception)

    def test_repr(self):
        e = DataTableError("bad table")
        assert "DataTableError(" in repr(e)
        assert "bad table" in repr(e)

    def test_str(self):
        e = DataTableError("bad table")
        assert "bad table" in str(e)


# ---------------------------------------------------------------------------
# DatabaseNotImplementedError
# ---------------------------------------------------------------------------


class TestDatabaseNotImplementedError:
    def test_str(self):
        e = DatabaseNotImplementedError("DuckDB", "notify")
        assert "DuckDB" in str(e)
        assert "notify" in str(e)

    def test_repr(self):
        e = DatabaseNotImplementedError("DuckDB", "notify")
        r = repr(e)
        assert "DatabaseNotImplementedError(" in r
        assert "DuckDB" in r


# ---------------------------------------------------------------------------
# File-format errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", [OdsFileError, XlsFileError, XlsxFileError])
def test_file_format_error(cls):
    e = cls("bad file")
    assert isinstance(e, Exception)
    assert "bad file" in repr(e)


# ---------------------------------------------------------------------------
# Parser errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", [CondParserError, NumericParserError])
def test_parser_error(cls):
    e = cls("parse failed")
    assert isinstance(e, Exception)
    assert "parse failed" in repr(e)


# ---------------------------------------------------------------------------
# ConsoleUIError
# ---------------------------------------------------------------------------


class TestConsoleUIError:
    def test_basic(self):
        e = ConsoleUIError("console error")
        assert isinstance(e, Exception)

    def test_value_stored(self):
        e = ConsoleUIError("console error")
        assert e.value == "console error"

    def test_repr(self):
        e = ConsoleUIError("console error")
        r = repr(e)
        assert "ConsoleUIError(" in r
        assert "console error" in r
