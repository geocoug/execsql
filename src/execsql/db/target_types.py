"""The execsql data type of each column of a table that IMPORT or COPY loads.

A load into a table that already exists converts each value by the type of
the column it goes into, not by the type scanned from the source data
(issue #100).  The adapters report each column's type: by the name their
catalog gives it (PostgreSQL, MySQL, SQL Server, DuckDB, Oracle), or by the
Python type their driver describes it with (Access, Firebird, ODBC DSNs).
The functions here turn that
into one of execsql's data types, or ``None`` when execsql has no
conversion that fits (arrays, JSON, UUIDs, enums, geometry, intervals, …).

Only the types that change how a value is converted are told apart: every
character type is :class:`DT_Text`, every integer type :class:`DT_Long`,
and so on.  A ``DECIMAL``/``NUMERIC``/``NUMBER`` with scale 0 holds whole
numbers only, so it is :class:`DT_Long` too.
"""

from __future__ import annotations

import datetime
import math
import re
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from execsql.exceptions import ErrInfo
from execsql.types import (
    DataType,
    DT_Binary,
    DT_Boolean,
    DT_Date,
    DT_Decimal,
    DT_Float,
    DT_Long,
    DT_Text,
    DT_Time,
    DT_Timestamp,
    DT_TimestampTZ,
)

__all__ = ["ColumnKinds", "existing_table_converter", "kind_for_python_type", "kind_for_type_name"]

#: Lower-cased column name -> the execsql type values for it convert to, or None.
ColumnKinds = dict[str, "type[DataType] | None"]

_TEXT = {
    "char",
    "character",
    "varchar",
    "character varying",
    "varchar2",
    "nchar",
    "national character",
    "nvarchar",
    "nvarchar2",
    "national character varying",
    "bpchar",
    "text",
    "ntext",
    "tinytext",
    "mediumtext",
    "longtext",
    "string",
    "clob",
    "nclob",
}
_INTEGER = {
    "integer",
    "int",
    "int1",
    "int2",
    "int4",
    "int8",
    "tinyint",
    "smallint",
    "mediumint",
    "bigint",
    "hugeint",
    "utinyint",
    "usmallint",
    "uinteger",
    "ubigint",
    "uhugeint",
    "serial",
    "smallserial",
    "bigserial",
}
_DECIMAL = {"decimal", "numeric", "number", "money", "smallmoney"}
_FLOAT = {"float", "float4", "float8", "real", "double", "double precision", "binary_float", "binary_double"}
_BOOLEAN = {"boolean", "bool"}
_TIMESTAMP = {
    "timestamp",
    "timestamp without time zone",
    "datetime",
    "datetime2",
    "smalldatetime",
    "timestamp_s",
    "timestamp_ms",
    "timestamp_ns",
}
_TIMESTAMPTZ = {"timestamptz", "timestamp with time zone", "timestamp with local time zone", "datetimeoffset"}
_TIME = {"time", "time without time zone"}
_BINARY = {
    "bytea",
    "blob",
    "tinyblob",
    "mediumblob",
    "longblob",
    "binary",
    "varbinary",
    "binary varying",
    "image",
    "raw",
    "long raw",
}

_PARAMS = re.compile(r"\(([^)]*)\)")


def kind_for_type_name(type_name: str, *, oracle: bool = False) -> type[DataType] | None:
    """The execsql type for a column declared as *type_name* (as the DBMS's catalog spells it).

    *oracle*: Oracle's ``DATE`` holds a time of day too, so it is a timestamp there.
    """
    name = type_name.strip().lower()
    if not name or "[" in name or name.endswith(" array"):
        return None
    params = _PARAMS.search(name)
    args = [a.strip() for a in params.group(1).split(",")] if params else []
    base = " ".join(_PARAMS.sub(" ", name).replace(" unsigned", " ").replace(" zerofill", " ").split())
    if base == "tinyint" and args == ["1"]:
        return DT_Boolean  # MySQL's BOOLEAN
    if base == "bit":
        # SQL Server's BIT; a wider BIT(n) is a bit string.
        return DT_Boolean if args in ([], ["1"]) else None
    if base in _TEXT:
        return DT_Text
    if base in _INTEGER:
        return DT_Long
    if base in _DECIMAL:
        if args[1:] == ["0"] or len(args) == 1:
            return DT_Long  # DECIMAL(p,0), NUMERIC(p), NUMBER(p): whole numbers
        return DT_Decimal
    if base in _FLOAT:
        return DT_Float
    if base in _BOOLEAN:
        return DT_Boolean
    if base == "date":
        return DT_Timestamp if oracle else DT_Date
    if base in _TIMESTAMP:
        return DT_Timestamp
    if base in _TIMESTAMPTZ:
        return DT_TimestampTZ
    if base in _TIME:
        return DT_Time
    if base in _BINARY:
        return DT_Binary
    return None


def kind_for_python_type(type_code: object, scale: object = None) -> type[DataType] | None:
    """The execsql type for a column a driver describes by the Python type it returns (pyodbc, firebird-driver).

    Binary columns are left out: pyodbc describes a SQL Server
    ``datetimeoffset`` as ``bytearray`` too.
    """
    if type_code is bool:
        return DT_Boolean
    if type_code is int:
        return DT_Long
    if type_code is float:
        return DT_Float
    if type_code is Decimal:
        return DT_Long if scale == 0 else DT_Decimal
    if type_code is str:
        return DT_Text
    if type_code is datetime.datetime:
        return DT_Timestamp
    if type_code is datetime.date:
        return DT_Date
    if type_code is datetime.time:
        return DT_Time
    return None


# ---------------------------------------------------------------------------
# Converting a value for the column it goes into
# ---------------------------------------------------------------------------

_INTEGER_TEXT = re.compile(r"^\s*[+-]?[0-9]+\s*$")
_NUMBER_TEXT = re.compile(r"^\s*[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\s*$")
# A whole number longer than this fits no integer column; it goes to the
# database as given, which rejects it, instead of being expanded here.
_MAX_INTEGER_DIGITS = 40

Converter = Callable[[Any], Any]


def _as_given(value: Any) -> Any:
    return value


def _whole_number_converter(column: str, table: str, default: Converter) -> Converter:
    """Convert a value for integer column *column*: a fraction is an error, never rounded.

    A value that is not a number (NULL, a date, a word) gets *default*, the
    conversion it had before, and the database takes or rejects that.
    """

    def convert(value: Any) -> Any:
        if isinstance(value, bool):
            return default(value)
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            if _INTEGER_TEXT.match(value):
                return int(value)
            if not _NUMBER_TEXT.match(value):
                return default(value)
            number = Decimal(value)
        elif isinstance(value, Decimal):
            number = value
        elif isinstance(value, float):
            if not math.isfinite(value):
                return default(value)
            number = Decimal(value)
        else:
            return default(value)
        if not number.is_finite() or number.adjusted() >= _MAX_INTEGER_DIGITS:
            return default(value)
        if number == number.to_integral_value():
            return int(number)
        raise ErrInfo(
            type="error",
            other_msg=(
                f"Can't load {value!r} into column {column} of {table}: the column holds whole numbers, "
                "and the database would round the value."
            ),
        )

    return convert


def _true_false_as_number(default: Converter) -> Converter:
    """Convert a value scanned as true/false for a number column: 1 or 0, read as before (``yes`` is 1)."""

    def convert(value: Any) -> Any:
        flag = default(value)
        return int(flag) if isinstance(flag, bool) else flag

    return convert


def existing_table_converter(
    kind: type[DataType] | None,
    scanned: type[DataType],
    default: Converter,
    column: str,
    table: str,
) -> Converter:
    """How a value for *column* of existing table *table* is converted.

    *kind* is the column's type (``None`` if execsql has none that fits),
    *scanned* the type the source column scanned as, and *default* the
    conversion to that scanned type, which a new table's values get.
    """
    if kind is DT_Text:
        return _as_given
    if kind in (DT_Long, DT_Decimal, DT_Float) and scanned is DT_Boolean:
        return _true_false_as_number(default)
    if kind is DT_Long:
        return _whole_number_converter(column, table, default)
    return default
