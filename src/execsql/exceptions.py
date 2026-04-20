from __future__ import annotations

"""
Custom exception hierarchy for execsql.

All domain-specific exceptions are defined here so that callers can import
from a single location.  Notable exceptions:

- :class:`ExecSqlError` — common base for all single-message execsql exceptions.
- :class:`ConfigError` — invalid or missing ``execsql.conf`` values.
- :class:`ErrInfo` — rich exception carrying type, command text, exception
  message, and script location; used as both a raised exception and an error
  data carrier passed to ``exit_now()``.
- :class:`ExecSqlTimeoutError` — timeout during alarm-timer operations.
- :class:`DataTypeError` / :class:`DbTypeError` — type-system failures.
- :class:`ColumnError` / :class:`DataTableError` — data-model failures.
- :class:`DatabaseNotImplementedError` — method not implemented for a DBMS.
- :class:`OdsFileError` / :class:`XlsFileError` / :class:`XlsxFileError`
  — spreadsheet I/O failures.
- :class:`ConsoleUIError` — GUI console errors.
- :class:`CondParserError` / :class:`NumericParserError` — parser failures.
"""

__all__ = [
    "ExecSqlError",
    "ConfigError",
    "ExecSqlTimeoutError",
    "ErrInfo",
    "DataTypeError",
    "DbTypeError",
    "ColumnError",
    "DataTableError",
    "DatabaseNotImplementedError",
    "OdsFileError",
    "XlsFileError",
    "XlsxFileError",
    "ConsoleUIError",
    "CondParserError",
    "NumericParserError",
]


class ExecSqlError(Exception):
    """Base class for simple single-message execsql exceptions.

    Subclasses inherit a ``value`` attribute holding the original message and
    a ``__repr__`` that uses the concrete class name, so no boilerplate is
    needed in each subclass.

    ``super().__init__(errmsg)`` is called so that ``str(exc)``, ``exc.args``,
    and standard logging all produce meaningful output.
    """

    def __init__(self, errmsg: str) -> None:
        super().__init__(errmsg)
        self.value = errmsg

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.value!r})"


class ConfigError(ExecSqlError):
    """Raised for invalid or missing execsql configuration values."""


class ExecSqlTimeoutError(ExecSqlError):
    """Timeout during alarm-timer operations.

    Inherits from :class:`ExecSqlError` so that generic ``except ExecSqlError``
    handlers will catch timeouts.  Accepts an optional message (defaults to
    ``"Operation timed out"``), keeping it compatible with bare
    ``raise ExecSqlTimeoutError`` usage.
    """

    def __init__(self, errmsg: str = "Operation timed out") -> None:
        super().__init__(errmsg)


class ErrInfo(ExecSqlError):
    """Rich exception and error-data carrier for execsql.

    ``str(e)`` returns the most informative available message (``other_msg``,
    then ``exception_msg``, then ``type``) so that standard logging and
    exception handlers produce useful output without requiring callers to know
    about the execsql-specific ``eval_err()`` / ``write()`` interface.

    ``eval_err()`` / ``write()`` remain available for the full formatted
    message including script location, timestamp, and command context.
    """

    def __repr__(self) -> str:
        return f"ErrInfo({self.type!r}, {self.command!r}, {self.exception!r}, {self.other!r})"

    def __str__(self) -> str:
        return self.other or self.exception or self.type or "ErrInfo"

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
        # Pass a concise message to Exception so str(e), e.args, and
        # standard loggers produce useful output.
        super().__init__(self.other or self.exception or self.type)

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
        elif self.type == "assert":
            self.error_message = "**** Assertion failed."
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


class DataTypeError(ExecSqlError):
    def __init__(self, data_type_name: str, error_msg: str) -> None:
        self.data_type_name = data_type_name or "Unspecified data type"
        self.error_msg = error_msg or "Unspecified error"
        super().__init__(str(self))

    def __repr__(self) -> str:
        return f"DataTypeError({self.data_type_name!r}, {self.error_msg!r})"

    def __str__(self) -> str:
        return f"{self.data_type_name}: {self.error_msg}"


class DbTypeError(ExecSqlError):
    def __init__(self, dbms_id: str, data_type: object, error_msg: str) -> None:
        self.dbms_id = dbms_id
        self.data_type = data_type
        self.error_msg = error_msg or "Unspecified error"
        super().__init__(str(self))

    def __repr__(self) -> str:
        return f"DbTypeError({self.dbms_id!r}, {self.data_type!r}, {self.error_msg!r})"

    def __str__(self) -> str:
        if self.data_type:
            return f"{self.dbms_id} DBMS type error with data type {self.data_type.data_type_name}: {self.error_msg}"
        else:
            return f"{self.dbms_id} DBMS type error: {self.error_msg}"


class ColumnError(ExecSqlError):
    """Raised for column-level data errors."""


class DataTableError(ExecSqlError):
    """Raised for DataTable-level errors."""


class DatabaseNotImplementedError(ExecSqlError):
    def __init__(self, db_name: str, method: str) -> None:
        self.db_name = db_name
        self.method = method
        super().__init__(str(self))

    def __repr__(self) -> str:
        return f"DatabaseNotImplementedError({self.db_name!r}, {self.method!r})"

    def __str__(self) -> str:
        return f"Method {self.method} is not implemented for database {self.db_name}"


class OdsFileError(ExecSqlError):
    """Raised for ODS file I/O errors."""


class XlsFileError(ExecSqlError):
    """Raised for XLS file I/O errors."""


class XlsxFileError(ExecSqlError):
    """Raised for XLSX file I/O errors."""


class ConsoleUIError(ExecSqlError):
    """Raised for GUI console errors."""


class CondParserError(ExecSqlError):
    """Raised for conditional-expression parse errors."""


class NumericParserError(ExecSqlError):
    """Raised for numeric-expression parse errors."""
