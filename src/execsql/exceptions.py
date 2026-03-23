from __future__ import annotations

"""
Custom exception hierarchy for execsql.

All domain-specific exceptions are defined here so that callers can import
from a single location.  Notable exceptions:

- :class:`ConfigError` — invalid or missing ``execsql.conf`` values.
- :class:`ErrInfo` — both an exception and a structured error-data carrier
  (type, command text, exception message, script location).
- :class:`ExecSqlTimeoutError` — timeout during alarm-timer operations.
- :class:`DataTypeError` / :class:`DbTypeError` — type-system failures.
- :class:`ColumnError` / :class:`DataTableError` — data-model failures.
- :class:`DatabaseNotImplementedError` — method not implemented for a DBMS.
- :class:`OdsFileError` / :class:`XlsFileError` / :class:`XlsxFileError`
  — spreadsheet I/O failures.
- :class:`ConsoleUIError` — GUI console errors.
- :class:`CondParserError` / :class:`NumericParserError` — parser failures.
"""


class ConfigError(Exception):
    def __init__(self, msg: str) -> None:
        self.value = msg

    def __repr__(self) -> str:
        return f"ConfigError({self.value!r})"


class ExecSqlTimeoutError(Exception):
    """Renamed from TimeoutError to avoid shadowing the Python 3.3+ built-in."""

    pass


class ErrInfo(Exception):
    """Both an exception and a data carrier for error information."""

    def __repr__(self) -> str:
        return f"ErrInfo({self.type!r}, {self.command!r}, {self.exception!r}, {self.other!r})"

    def __init__(
        self,
        type: str,
        command_text: str | None = None,
        exception_msg: str | None = None,
        other_msg: str | None = None,
    ) -> None:
        self.type = type
        self.command = command_text
        self.exception = None if not exception_msg else exception_msg.replace("\n", "\n     ")
        self.other = None if not other_msg else other_msg.replace("\n", "\n     ")
        self.script_file = None
        self.script_line_no = None
        self.cmd = None
        self.cmdtype = None
        self.error_message = None

    def script_info(self) -> str | None:
        if self.script_line_no:
            return f"Line {self.script_line_no} of script {self.script_file}"
        return None

    def cmd_info(self) -> str | None:
        if self.cmdtype:
            if self.cmdtype == "cmd":
                return f"Metacommand: {self.cmd}"
            else:
                return f"SQL statement: \n         {self.cmd.replace(chr(10), chr(10) + '         ')}"
        return None

    def eval_err(self) -> str:
        import time

        if self.type == "db":
            self.error_message = "**** Error in SQL statement."
        elif self.type == "cmd":
            self.error_message = "**** Error in metacommand."
        elif self.type == "log":
            self.error_message = "**** Error in logging."
        elif self.type == "error":
            self.error_message = "**** General error."
        elif self.type == "systemexit":
            self.error_message = "**** Exit."
        elif self.type == "exception":
            self.error_message = "**** Exception."
        else:
            self.error_message = f"**** Error of unknown type: {self.type}"
        sinfo = self.script_info()
        cinfo = self.cmd_info()
        if sinfo:
            self.error_message += f"\n     {sinfo}"
        if self.exception:
            self.error_message += f"\n     {self.exception}"
        if self.other:
            self.error_message += f"\n     {self.other}"
        if self.command:
            self.error_message += f"\n     {self.command}"
        if cinfo:
            self.error_message += f"\n     {cinfo}"
        self.error_message += f"\n     Error occurred at {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC."
        return self.error_message

    def write(self) -> str:
        import sys

        errmsg = self.eval_err()
        sys.stderr.write(errmsg + "\n")
        return errmsg

    def errmsg(self) -> str:
        return self.eval_err()


class DataTypeError(Exception):
    def __init__(self, data_type_name: str, error_msg: str) -> None:
        self.data_type_name = data_type_name or "Unspecified data type"
        self.error_msg = error_msg or "Unspecified error"

    def __repr__(self) -> str:
        return f"DataTypeError({self.data_type_name!r}, {self.error_msg!r})"

    def __str__(self) -> str:
        return f"{self.data_type_name}: {self.error_msg}"


class DbTypeError(Exception):
    def __init__(self, dbms_id: str, data_type: object, error_msg: str) -> None:
        self.dbms_id = dbms_id
        self.data_type = data_type
        self.error_msg = error_msg or "Unspecified error"

    def __repr__(self) -> str:
        return f"DbTypeError({self.dbms_id!r}, {self.data_type!r}, {self.error_msg!r})"

    def __str__(self) -> str:
        if self.data_type:
            return f"{self.dbms_id} DBMS type error with data type {self.data_type.data_type_name}: {self.error_msg}"
        else:
            return f"{self.dbms_id} DBMS type error: {self.error_msg}"


class ColumnError(Exception):
    def __init__(self, errmsg: str) -> None:
        self.value = errmsg

    def __repr__(self) -> str:
        return f"ColumnError({self.value!r})"

    def __str__(self) -> str:
        return repr(self.value)


class DataTableError(Exception):
    def __init__(self, errmsg: str) -> None:
        self.value = errmsg

    def __repr__(self) -> str:
        return f"DataTableError({self.value})"

    def __str__(self) -> str:
        return repr(self.value)


class DatabaseNotImplementedError(Exception):
    def __init__(self, db_name: str, method: str) -> None:
        self.db_name = db_name
        self.method = method

    def __repr__(self) -> str:
        return f"DatabaseNotImplementedError({self.db_name!r}, {self.method!r})"

    def __str__(self) -> str:
        return f"Method {self.method} is not implemented for database {self.db_name}"


class OdsFileError(Exception):
    def __init__(self, errmsg: str) -> None:
        self.value = errmsg

    def __repr__(self) -> str:
        return f"OdsFileError({self.value!r})"


class XlsFileError(Exception):
    def __init__(self, errmsg: str) -> None:
        self.value = errmsg

    def __repr__(self) -> str:
        return f"XlsFileError({self.value!r})"


class XlsxFileError(Exception):
    def __init__(self, errmsg: str) -> None:
        self.value = errmsg

    def __repr__(self) -> str:
        return f"XlsxFileError({self.value!r})"


class ConsoleUIError(Exception):
    def __init__(self, errmsg: str) -> None:
        self.value = errmsg

    def __repr__(self) -> str:
        return f"ConsoleUIError({self.value!r})"


class CondParserError(Exception):
    def __init__(self, errmsg: str) -> None:
        self.value = errmsg

    def __repr__(self) -> str:
        return f"CondParserError({self.value!r})"


class NumericParserError(Exception):
    def __init__(self, errmsg: str) -> None:
        self.value = errmsg

    def __repr__(self) -> str:
        return f"NumericParserError({self.value!r})"
