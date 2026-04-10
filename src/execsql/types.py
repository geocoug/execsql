from __future__ import annotations

"""
Data-type system and per-DBMS SQL type dialect mappings.

Defines the abstract :class:`DataType` base class and all concrete subclasses
used by the column-inference engine (:mod:`execsql.models`) and by database
adapters when generating ``CREATE TABLE`` statements.

Data type classes (most-specific first in inference order):

- :class:`DT_TimestampTZ` — timezone-aware timestamp
- :class:`DT_Timestamp` — naive timestamp / datetime
- :class:`DT_Date` — calendar date
- :class:`DT_Time` — time of day; :class:`DT_Time_Oracle` — Oracle VARCHAR
  fallback
- :class:`DT_Boolean` — true/false; recognises word and integer forms
- :class:`DT_Integer` — small integer (≤ max_int config)
- :class:`DT_Long` — large integer (Python ``int``)
- :class:`DT_Float` — IEEE double
- :class:`DT_Decimal` — exact decimal (``decimal.Decimal``)
- :class:`DT_Character` — fixed-length string ≤ 255 chars
- :class:`DT_Varchar` — variable-length string ≤ 255 chars
- :class:`DT_Text` — unbounded string
- :class:`DT_Binary` — byte array

The :class:`DbType` class maps Python ``DataType`` subclasses to DBMS-specific
SQL type names for a given backend.  Pre-built :class:`DbType` instances are
provided at module level for every supported DBMS:
``dbt_postgres``, ``dbt_sqlite``, ``dbt_duckdb``, ``dbt_sqlserver``,
``dbt_access``, ``dbt_dsn``, ``dbt_mysql``, ``dbt_firebird``, ``dbt_oracle``.
"""

import collections
import datetime
import re
from decimal import Decimal

from execsql.exceptions import DataTypeError, DbTypeError
from execsql.utils.numeric import leading_zero_num

__all__ = [
    "DataType",
    "DT_TimestampTZ",
    "DT_Timestamp",
    "DT_Date",
    "DT_Time",
    "DT_Time_Oracle",
    "DT_Boolean",
    "DT_Integer",
    "DT_Long",
    "DT_Float",
    "DT_Decimal",
    "DT_Character",
    "DT_Varchar",
    "DT_Text",
    "DT_Binary",
    "DbType",
    "dbt_postgres",
    "dbt_sqlite",
    "dbt_duckdb",
    "dbt_sqlserver",
    "dbt_access",
    "dbt_dsn",
    "dbt_mysql",
    "dbt_firebird",
    "dbt_oracle",
]


class DataType:
    """Abstract base class for all data-type matchers used during column inference."""

    data_type_name = None
    data_type = None
    lenspec = False  # Is a length specification required for a (SQL) declaration of this data type?
    varlen = False  # Do we need to know if a set of data values varies in length?
    precspec = False  # Do we need to know the precision and scale of the data?
    precision = None  # Precision (total number of digits) for numeric values.
    scale = None  # Scale (number of digits to the right of the decimal point) for numeric values.
    _CONV_ERR = "Can't convert %s"

    def __repr__(self) -> str:
        return f"DataType({self.data_type_name!r}, {self.data_type!r})"

    def is_null(self, data: object) -> bool:
        """Return True if the data value is None."""
        return data is None

    def matches(self, data: object) -> bool:
        """Return True if the non-null data value could be of this data type."""
        # Returns T/F indicating whether the given data value could be of this data type.
        # The data value should be non-null.
        if self.is_null(data):
            return False
        return self._is_match(data)

    def from_data(self, data: object) -> object:
        """Coerce the data value to this type or raise DataTypeError."""
        # Returns the data value coerced to this type, or raises a DataTypeError exception.
        # The data value should be non-null.
        if self.is_null(data):
            return None
        return self._from_data(data)

    def _is_match(self, data: object) -> bool:
        # This method may be overridden in child classes.
        if data is None:
            return False
        try:
            self._from_data(data)
        except DataTypeError:
            return False
        return True

    def _from_data(self, data: object) -> object:
        # This method may be overridden in child classes.
        if data is None:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % "NULL")
        if type(data) is self.data_type:
            return data
        try:
            i = self.data_type(data)
        except Exception as e:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % data) from e
        return i


class DT_TimestampTZ(DataType):
    """Timezone-aware timestamp data type."""

    data_type_name = "timestamptz"
    data_type = datetime.datetime
    # There is no distinct Python type corresponding to a timestamptz, so the data_type
    # is not exactly appropriate, and methods need to be overridden.

    def __repr__(self) -> str:
        return "DT_TimestampTZ()"

    def _is_match(self, data: object) -> bool:
        if data is None:
            return False
        if isinstance(data, datetime.datetime):
            return bool(data.tzinfo is not None and data.tzinfo.utcoffset(data) is not None)
        if not isinstance(data, str):
            return False
        try:
            self.from_data(data)
        except DataTypeError:
            return False
        return True

    def _from_data(self, data: object) -> object:
        from execsql.utils.datetime import parse_datetimetz

        if data is None:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % "NULL")
        dt = parse_datetimetz(data)
        if not dt:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % data)
        return dt


class DT_Timestamp(DataType):
    """Naive timestamp (datetime without timezone) data type."""

    data_type_name = "timestamp"
    data_type = datetime.datetime

    def __repr__(self) -> str:
        return "DT_Timestamp()"

    def _from_data(self, data: object) -> object:
        from execsql.utils.datetime import parse_datetime

        if data is None:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % "NULL")
        dt = parse_datetime(data)
        if not dt:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % data)
        return dt


date_fmts = collections.deque(
    (
        "%x",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%b %d, %Y",
        "%b %d %Y",
        "%d %b, %Y",
        "%d %b %Y",
        "%b. %d, %Y",
        "%b. %d %Y",
        "%d %b., %Y",
        "%d %b. %Y",
        "%B %d, %Y",
        "%B %d %Y",
        "%d %B, %Y",
        "%d %B %Y",
    ),
)


class DT_Date(DataType):
    """Calendar date data type with multiple format recognition."""

    data_type_name = "date"
    data_type = datetime.date

    def __init__(self) -> None:
        """Initialise the date format deque for adaptive format matching."""
        self._date_fmts = collections.deque(date_fmts)

    def __repr__(self) -> str:
        return "DT_Date()"

    def _from_data(self, data: object) -> object:
        if data is None:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % "NULL")
        if type(data) is self.data_type:
            return data
        if not isinstance(data, str):
            raise DataTypeError(self.data_type_name, self._CONV_ERR % data)
        for i, f in enumerate(self._date_fmts):  # noqa: B007
            try:
                dt = datetime.datetime.strptime(data, f)
                dtt = datetime.date(dt.year, dt.month, dt.day)
            except Exception:
                continue
            break
        else:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % data)
        if i:
            del self._date_fmts[i]
            self._date_fmts.appendleft(f)
        return dtt


class DT_Time(DataType):
    """Time-of-day data type with multiple format recognition."""

    data_type_name = "time"
    data_type = datetime.time
    time_fmts = (
        "%H:%M",
        "%H%M:%S",
        "%H%M:%S.%f",
        "%H:%M:%S",
        "%H:%M:%S.%f",
        "%I:%M%p",
        "%I:%M:%S%p",
        "%I:%M:%S.%f%p",
        "%I:%M %p",
        "%I:%M:%S %p",
        "%I:%M:%S.%f %p",
        "%X",
    )

    def __repr__(self) -> str:
        return "DT_Time()"

    def _from_data(self, data: object) -> object:
        if data is None:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % "NULL")
        if type(data) is self.data_type:
            return data
        if isinstance(data, datetime.datetime):
            return datetime.time(data.hour, data.minute, data.second, data.microsecond)
        if not isinstance(data, str):
            raise DataTypeError(self.data_type_name, self._CONV_ERR % data)
        for f in self.time_fmts:
            try:
                dt = datetime.datetime.strptime(data, f)
                t = datetime.time(dt.hour, dt.minute, dt.second, dt.microsecond)
            except Exception:
                continue
            break
        else:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % data)
        return t


class DT_Time_Oracle(DT_Time):
    """Oracle-specific time type stored as VARCHAR2 with length specification."""

    lenspec = True
    varlen = True


class DT_Boolean(DataType):
    """Boolean data type recognising word and integer true/false forms."""

    data_type_name = "boolean"
    data_type = bool

    def __repr__(self) -> str:
        return "DT_Boolean()"

    def set_bool_matches(self) -> None:
        """Populate the true/false match tuples from the current configuration."""
        import execsql.state as _state

        conf = _state.conf
        self.true = ("yes", "true")
        self.false = ("no", "false")
        if not conf.boolean_words:
            self.true += ("y", "t")
            self.false += ("n", "f")
        if conf.boolean_int:
            self.true += ("1",)
            self.false += ("0",)
        self.bool_repr = self.true + self.false

    def _is_match(self, data: object) -> bool:
        import execsql.state as _state

        conf = _state.conf
        if data is None:
            return False
        self.set_bool_matches()
        return bool(
            isinstance(data, bool)
            or conf.boolean_int
            and type(data) is int
            and data in (0, 1)
            or isinstance(data, str)
            and data.lower() in self.bool_repr,
        )

    def _from_data(self, data: object) -> object:
        import execsql.state as _state

        conf = _state.conf
        if data is None:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % "NULL")
        self.set_bool_matches()
        if isinstance(data, bool):
            return data
        elif conf.boolean_int and type(data) is int and data in (0, 1):
            return data == 1
        elif isinstance(data, str) and data.lower() in self.bool_repr:
            return data.lower() in self.true
        else:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % data)


class DT_Integer(DataType):
    """Small integer data type bounded by the configured max_int."""

    data_type_name = "integer"
    data_type = int

    def __repr__(self) -> str:
        return "DT_Integer()"

    def _is_match(self, data: object) -> bool:
        import execsql.state as _state

        conf = _state.conf
        if type(data) is int:
            return data <= conf.max_int and data >= -1 * conf.max_int - 1
        elif isinstance(data, float):
            return False
        elif isinstance(data, str):
            if leading_zero_num(data):
                return False
            if not re.match(r"^\s*[+-]?\d+\s*$", data):
                return False
            try:
                i = int(data)
            except Exception:
                return False
            return i <= conf.max_int and i >= -1 * conf.max_int - 1
        else:
            return False

    def _from_data(self, data: object) -> object:
        if data is None:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % "NULL")
        if type(data) is int:
            return data
        if isinstance(data, float):
            if int(data) == data:
                return int(data)
            else:
                raise DataTypeError(self.data_type_name, self._CONV_ERR % data)
        if isinstance(data, str) and not re.match(r"^\s*[+-]?\d+\s*$", data):
            raise DataTypeError(self.data_type_name, self._CONV_ERR % data)
        try:
            i = int(data)
        except Exception as e:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % data) from e
        if leading_zero_num(data):
            raise DataTypeError(self.data_type_name, self._CONV_ERR % data)
        return i


class DT_Long(DataType):
    """Large integer (bigint) data type using Python int."""

    data_type_name = "long"
    data_type = int  # In Python 3, long is just int

    def __repr__(self) -> str:
        return "DT_Long()"

    def _from_data(self, data: object) -> object:
        import math as _math

        if data is None:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % "NULL")
        if type(data) is int:
            return data
        if isinstance(data, float):
            if _math.isnan(data):
                return None
            else:
                if int(data) == data:
                    return int(data)
            raise DataTypeError(self.data_type_name, self._CONV_ERR % data)
        if isinstance(data, Decimal):
            raise DataTypeError(self.data_type_name, self._CONV_ERR % data)
        if leading_zero_num(data):
            raise DataTypeError(self.data_type_name, self._CONV_ERR % data)
        if isinstance(data, str) and not data.isdigit():
            raise DataTypeError(self.data_type_name, self._CONV_ERR % data)
        try:
            i = int(data)
        except Exception as e:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % data) from e
        return i


class DT_Float(DataType):
    """IEEE double-precision floating-point data type."""

    data_type_name = "float"
    data_type = float

    def __repr__(self) -> str:
        return "DT_Float()"

    def _is_match(self, data: object) -> bool:
        if data is None:
            return False
        if isinstance(data, float):
            return True
        if leading_zero_num(data):
            return False
        if isinstance(data, str) and not re.match(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$", data):
            return False
        try:
            float(data)
        except Exception:
            return False
        return True

    def _from_data(self, data: object) -> object:
        if data is None:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % "NULL")
        if isinstance(data, float):
            return data
        if leading_zero_num(data):
            raise DataTypeError(self.data_type_name, self._CONV_ERR % data)
        if isinstance(data, str) and not re.match(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$", data):
            raise DataTypeError(self.data_type_name, self._CONV_ERR % data)
        try:
            i = float(data)
        except Exception as e:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % data) from e
        return i


class DT_Decimal(DataType):
    """Exact decimal data type tracking precision and scale."""

    data_type_name = "decimal"
    data_type = Decimal
    precspec = True

    def __repr__(self) -> str:
        return "DT_Decimal()"

    def set_scale_prec(self, dec: Decimal) -> None:
        """Compute and store the precision and scale from a Decimal value."""
        # 'dec' should be Decimal.
        x = dec.as_tuple()
        digits = len(x.digits)
        if x.exponent < 0 and abs(x.exponent) > digits:
            self.precision = abs(x.exponent) + 1
        else:
            self.precision = digits
        self.scale = abs(x.exponent)

    def _from_data(self, data: object) -> object:
        if data is None:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % "NULL")
        if leading_zero_num(data):
            raise DataTypeError(self.data_type_name, self._CONV_ERR % data)
        if isinstance(data, Decimal):
            self.set_scale_prec(data)
            return data
        elif isinstance(data, str):
            if not re.match(r"^[+-]?(\d+(\.\d*)?|\.\d+)$", data):
                raise DataTypeError(self.data_type_name, self._CONV_ERR % data)
            try:
                dec = Decimal(data)
            except Exception as e:
                raise DataTypeError(self.data_type_name, self._CONV_ERR % data) from e
            self.set_scale_prec(dec)
            return dec
        raise DataTypeError(self.data_type_name, self._CONV_ERR % data)


class DT_Character(DataType):
    """Fixed-length string data type (up to 255 characters)."""

    data_type_name = "character"
    lenspec = True

    def __repr__(self) -> str:
        return "DT_Character()"

    def _is_match(self, data: object) -> bool:
        if isinstance(data, bytearray):
            return False
        return super()._is_match(data)

    def _from_data(self, data: object) -> object:
        # data must be non-null.
        # This identifies data as character only if it is convertible to a string and its
        # length is no more than 255 characters.
        if data is None:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % "NULL")
        data_type = str
        if not isinstance(data, str):
            try:
                data = data_type(data)
            except ValueError as e:
                raise DataTypeError(self.data_type_name, self._CONV_ERR % data) from e
            if len(data) > 255:
                raise DataTypeError(self.data_type_name, self._CONV_ERR % data)
        return data


class DT_Varchar(DataType):
    """Variable-length string data type (up to 255 characters)."""

    data_type_name = "varchar"
    lenspec = True
    varlen = True

    def __repr__(self) -> str:
        return "DT_Varchar()"

    def _is_match(self, data: object) -> bool:
        if isinstance(data, bytearray):
            return False
        return super()._is_match(data)

    def _from_data(self, data: object) -> object:
        # This varchar data type is the same as the character data type.
        if data is None:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % "NULL")
        data_type = str
        if isinstance(data, str):
            try:
                data = data_type(data)
            except ValueError as e:
                raise DataTypeError(self.data_type_name, self._CONV_ERR % data) from e
            if len(data) > 255:
                raise DataTypeError(self.data_type_name, self._CONV_ERR % data)
        return data


class DT_Text(DataType):
    """Unbounded text string data type."""

    data_type_name = "character"

    def __repr__(self) -> str:
        return "DT_Text()"

    def _is_match(self, data: object) -> bool:
        if isinstance(data, bytearray):
            return False
        return super()._is_match(data)

    def _from_data(self, data: object) -> object:
        if data is None:
            raise DataTypeError(self.data_type_name, self._CONV_ERR % "NULL")
        data_type = str
        if not isinstance(data, str):
            try:
                data = data_type(data)
            except ValueError as e:
                raise DataTypeError(self.data_type_name, self._CONV_ERR % data) from e
        return data


class DT_Binary(DataType):
    """Binary byte-array data type."""

    data_type_name = "binary"
    data_type = bytearray

    def __repr__(self) -> str:
        return "DT_Binary()"


class DbType:
    """Map Python DataType subclasses to DBMS-specific SQL type names."""

    def __init__(self, DBMS_id: str, db_obj_quotes: str = '""') -> None:
        """Initialise a DBMS dialect with its identifier and quoting characters."""
        # The DBMS_id is the name by which this DBMS is identified.
        # db_obj_quotechars is a string of two characters that are the opening and closing quotes
        # for identifiers (schema, table, and column names) that need to be quoted.
        self.dbms_id = DBMS_id
        self.quotechars = db_obj_quotes
        # The dialect is a dictionary of DBMS-specific names for each column type.
        # Dialect keys are DataType classes.
        # Dialect objects are 4-tuples consisting of:
        #   0. a data type name (str)--non-null
        #   1. a Boolean indicating whether or not the length is part of the data type definition
        #   2. a name to use with the 'cast' operator as an alternative to the data type name--nullable.
        #   3. a function to perform a dbms-specific modification of the type conversion result
        #   4. the precision for numeric data types.
        #   5. the scale for numeric data types.
        self.dialect = None
        # The dt_xlate dictionary translates one data type to another.
        self.dt_xlate: dict = {}

    def __repr__(self) -> str:
        return f"DbType({self.dbms_id!r}, {self.quotechars!r})"

    def name_datatype(
        self,
        data_type: object,
        dbms_name: str,
        length_required: bool = False,
        casting_name: object = None,
        conv_mod_fn: object = None,
        precision: object = None,
        scale: object = None,
    ) -> None:
        """Register a DBMS-specific SQL type name for a DataType class."""
        # data_type is a DataType class object.
        # dbms_name is the DBMS-specific name for this data type.
        # length_required indicates whether length information is required.
        # casting_name is an alternate to the data type name to use in SQL "cast(x as <casting_name>)" expressions.
        # conv_mod_fn is a function that modifies the result of data_type().from_data(x).
        if self.dialect is None:
            self.dialect = {}
        self.dialect[data_type] = (dbms_name, length_required, casting_name, conv_mod_fn, precision, scale)

    def datatype_name(self, data_type: object) -> str:
        """Return the DBMS-specific SQL type name for the given DataType class."""
        # A convenience function to simplify access to data type names.
        try:
            return self.dialect[data_type][0]
        except Exception as e:
            raise DbTypeError(
                self.dbms_id,
                data_type,
                f"{self.dbms_id} DBMS type has no specification for data type {data_type.data_type_name}",
            ) from e

    def quoted(self, dbms_object: str) -> str:
        """Quote a database identifier if it contains non-word characters."""
        if re.search(r"\W", dbms_object):
            if self.quotechars[0] == self.quotechars[1] and self.quotechars[0] in dbms_object:
                dbms_object = dbms_object.replace(self.quotechars[0], self.quotechars[0] + self.quotechars[0])
            return self.quotechars[0] + dbms_object + self.quotechars[1]
        return dbms_object

    def spec_type(self, data_type: object) -> object:
        """Return the translated data type, or the original if no translation exists."""
        # Returns a translated data type or the original if there is no translation.
        if data_type in self.dt_xlate:
            return self.dt_xlate[data_type]
        return data_type

    def column_spec(
        self,
        column_name: str,
        data_type: object,
        max_len: object = None,
        is_nullable: bool = False,
        precision: object = None,
        scale: object = None,
    ) -> str:
        """Return a column specification string suitable for a CREATE TABLE statement."""
        # Returns a column specification as it would be used in a CREATE TABLE statement.
        data_type = self.spec_type(data_type)
        try:
            dts = self.dialect[data_type]
        except Exception as e:
            raise DbTypeError(
                self.dbms_id,
                data_type,
                f"{self.dbms_id} DBMS type has no specification for data type {data_type.data_type_name}",
            ) from e
        if max_len and max_len > 0 and dts[1]:
            spec = f"{self.quoted(column_name)} {dts[0]}({max_len})"
        elif data_type.precspec and precision and scale:
            # numeric
            spec = f"{self.quoted(column_name)} {dts[0]}({precision},{scale})"
        else:
            spec = f"{self.quoted(column_name)} {dts[0]}"
        if not is_nullable:
            spec += " NOT NULL"
        return spec


# Create a DbType object for each DBMS supported by execsql.

dbt_postgres = DbType("PostgreSQL")
dbt_postgres.name_datatype(DT_TimestampTZ, "timestamp with time zone")
dbt_postgres.name_datatype(DT_Timestamp, "timestamp")
dbt_postgres.name_datatype(DT_Date, "date")
dbt_postgres.name_datatype(DT_Time, "time")
dbt_postgres.name_datatype(DT_Integer, "integer")
dbt_postgres.name_datatype(DT_Long, "bigint")
dbt_postgres.name_datatype(DT_Float, "double precision")
dbt_postgres.name_datatype(DT_Decimal, "numeric")
dbt_postgres.name_datatype(DT_Boolean, "boolean")
dbt_postgres.name_datatype(DT_Character, "character", True)
dbt_postgres.name_datatype(DT_Varchar, "character varying", True)
dbt_postgres.name_datatype(DT_Text, "text")
dbt_postgres.name_datatype(DT_Binary, "bytea")

dbt_sqlite = DbType("SQLite")
dbt_sqlite.name_datatype(DT_TimestampTZ, "timestamp with time zone")
dbt_sqlite.name_datatype(DT_Timestamp, "timestamp")
dbt_sqlite.name_datatype(DT_Date, "date")
dbt_sqlite.name_datatype(DT_Time, "time")
dbt_sqlite.name_datatype(DT_Integer, "integer")
dbt_sqlite.name_datatype(DT_Long, "hugeint")
dbt_sqlite.name_datatype(DT_Float, "double")
dbt_sqlite.name_datatype(DT_Decimal, "decimal")
dbt_sqlite.name_datatype(DT_Boolean, "boolean")
dbt_sqlite.name_datatype(DT_Character, "varchar")
dbt_sqlite.name_datatype(DT_Varchar, "varchar")
dbt_sqlite.name_datatype(DT_Text, "varchar")
dbt_sqlite.name_datatype(DT_Binary, "blob")

dbt_duckdb = DbType("DuckDB")
dbt_duckdb.name_datatype(DT_TimestampTZ, "TIMESTAMPTZ")
dbt_duckdb.name_datatype(DT_Timestamp, "TIMESTAMP")
dbt_duckdb.name_datatype(DT_Date, "DATE")
dbt_duckdb.name_datatype(DT_Time, "TIME")
dbt_duckdb.name_datatype(DT_Integer, "INTEGER")
dbt_duckdb.name_datatype(DT_Long, "BIGINT")
dbt_duckdb.name_datatype(DT_Float, "REAL")
dbt_duckdb.name_datatype(DT_Decimal, "NUMERIC")
dbt_duckdb.name_datatype(DT_Boolean, "BOOLEAN")
dbt_duckdb.name_datatype(DT_Character, "TEXT")
dbt_duckdb.name_datatype(DT_Varchar, "TEXT")
dbt_duckdb.name_datatype(DT_Text, "TEXT")
dbt_duckdb.name_datatype(DT_Binary, "BLOB")

dbt_sqlserver = DbType("SQL Server")
dbt_sqlserver.name_datatype(DT_TimestampTZ, "varchar", True)
dbt_sqlserver.name_datatype(DT_Timestamp, "datetime")
dbt_sqlserver.name_datatype(DT_Date, "date")
dbt_sqlserver.name_datatype(DT_Time, "time")
dbt_sqlserver.name_datatype(DT_Integer, "int")
dbt_sqlserver.name_datatype(DT_Long, "bigint")
dbt_sqlserver.name_datatype(DT_Float, "double precision")
dbt_sqlserver.name_datatype(DT_Decimal, "decimal")
dbt_sqlserver.name_datatype(DT_Boolean, "bit")
dbt_sqlserver.name_datatype(DT_Character, "character", True)
dbt_sqlserver.name_datatype(DT_Varchar, "varchar", True)
dbt_sqlserver.name_datatype(DT_Text, "varchar(max)")
dbt_sqlserver.name_datatype(DT_Binary, "varbinary(max)")

dbt_access = DbType("Access")
dbt_access.name_datatype(DT_TimestampTZ, "VARCHAR", True)
dbt_access.name_datatype(DT_Timestamp, "VARCHAR", True)
dbt_access.name_datatype(DT_Date, "VARCHAR", True)
dbt_access.name_datatype(DT_Time, "VARCHAR", True)
dbt_access.name_datatype(DT_Integer, "LONG")
dbt_access.name_datatype(DT_Long, "DOUBLE")
dbt_access.name_datatype(DT_Float, "DOUBLE")
dbt_access.name_datatype(DT_Decimal, "NUMERIC")
dbt_access.dt_xlate[DT_Decimal] = DT_Float
dbt_access.name_datatype(DT_Boolean, "LONG")
dbt_access.name_datatype(DT_Character, "VARCHAR", True)
dbt_access.name_datatype(DT_Varchar, "VARCHAR", True)
dbt_access.name_datatype(DT_Text, "LONGTEXT")
dbt_access.name_datatype(DT_Binary, "LONGBINARY")

dbt_dsn = DbType("DSN")
dbt_dsn.name_datatype(DT_TimestampTZ, "VARCHAR", True)
dbt_dsn.name_datatype(DT_Timestamp, "VARCHAR", True)
dbt_dsn.name_datatype(DT_Date, "VARCHAR", True)
dbt_dsn.name_datatype(DT_Time, "VARCHAR", True)
dbt_dsn.name_datatype(DT_Integer, "LONG")
dbt_dsn.name_datatype(DT_Long, "DOUBLE")
dbt_dsn.name_datatype(DT_Float, "DOUBLE")
dbt_dsn.name_datatype(DT_Decimal, "NUMERIC")
dbt_dsn.name_datatype(DT_Boolean, "LONG")
dbt_dsn.name_datatype(DT_Character, "VARCHAR", True)
dbt_dsn.name_datatype(DT_Varchar, "VARCHAR", True)
dbt_dsn.name_datatype(DT_Text, "LONGTEXT")
dbt_dsn.name_datatype(DT_Binary, "LONGBINARY")

dbt_mysql = DbType("MySQL")
dbt_mysql.name_datatype(DT_TimestampTZ, "varchar", True, "char")
dbt_mysql.name_datatype(DT_Timestamp, "datetime", conv_mod_fn=lambda x: x if x is not None else "")
dbt_mysql.name_datatype(DT_Date, "date", conv_mod_fn=lambda x: x if x is not None else "")
dbt_mysql.name_datatype(DT_Time, "time")
dbt_mysql.name_datatype(DT_Integer, "integer", False, "signed integer")
dbt_mysql.name_datatype(DT_Long, "bigint", False, "signed integer")
dbt_mysql.name_datatype(DT_Float, "double precision", False, "binary")
dbt_mysql.name_datatype(DT_Decimal, "numeric")
dbt_mysql.name_datatype(
    DT_Boolean,
    "boolean",
    False,
    "binary",
    conv_mod_fn=lambda x: int(x) if x is not None else None,
)
dbt_mysql.name_datatype(DT_Character, "character", True, "char")
dbt_mysql.name_datatype(DT_Varchar, "character varying", True, "char")
dbt_mysql.name_datatype(DT_Text, "longtext", False, "char")
dbt_mysql.name_datatype(DT_Binary, "longblob", False, "binary")

dbt_firebird = DbType("Firebird")
dbt_firebird.name_datatype(DT_TimestampTZ, "CHAR", True)
dbt_firebird.name_datatype(DT_Timestamp, "TIMESTAMP")
dbt_firebird.name_datatype(DT_Date, "DATE")
dbt_firebird.name_datatype(DT_Time, "TIME")
dbt_firebird.name_datatype(DT_Integer, "INTEGER")
dbt_firebird.name_datatype(DT_Long, "BIGINT")
dbt_firebird.name_datatype(DT_Float, "DOUBLE PRECISION")
dbt_firebird.name_datatype(DT_Decimal, "NUMERIC")
dbt_firebird.name_datatype(
    DT_Boolean,
    "INTEGER",
    conv_mod_fn=lambda x: int(x) if x is not None else None,
)
dbt_firebird.name_datatype(DT_Character, "CHAR", True)
dbt_firebird.name_datatype(DT_Varchar, "VARCHAR", True)
dbt_firebird.name_datatype(DT_Text, "BLOB")
dbt_firebird.name_datatype(DT_Binary, "BLOB")

dbt_oracle = DbType("Oracle")
dbt_oracle.name_datatype(DT_TimestampTZ, "TIMESTAMP WITH TIME ZONE")
dbt_oracle.name_datatype(DT_Timestamp, "TIMESTAMP", casting_name="TIMESTAMP")
dbt_oracle.name_datatype(DT_Date, "DATE", casting_name="DATE")
dbt_oracle.name_datatype(DT_Time_Oracle, "VARCHAR2", True, casting_name="VARCHAR(20)")
dbt_oracle.name_datatype(DT_Integer, "NUMBER")
dbt_oracle.name_datatype(DT_Long, "NUMBER")
dbt_oracle.name_datatype(DT_Float, "FLOAT")
dbt_oracle.name_datatype(DT_Decimal, "NUMBER")
dbt_oracle.name_datatype(
    DT_Boolean,
    "INTEGER",
    conv_mod_fn=lambda x: int(x) if x is not None else None,
)
dbt_oracle.name_datatype(DT_Character, "CHAR", True)
dbt_oracle.name_datatype(DT_Varchar, "NVARCHAR2", True)
dbt_oracle.name_datatype(DT_Text, "CLOB")
dbt_oracle.name_datatype(DT_Binary, "BLOB")
