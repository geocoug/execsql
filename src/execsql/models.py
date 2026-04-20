from __future__ import annotations

"""
Data-type inference models for auto-creating database tables from raw data.

When execsql imports a CSV, ODS, or spreadsheet file it needs to infer a
column type for each column so it can generate a ``CREATE TABLE`` statement.
This module provides:

- :class:`Column` — scans a stream of values and accumulates type-match
  counters (most-specific first: TimestampTZ → … → Text → Binary).
  ``column_type()`` returns the winning type as a 6-tuple.
- :class:`DataTable` — wraps a list of ``Column`` objects and a row
  iterator; drives ``Column.eval_types()`` for every row.  Produces
  ``CREATE TABLE`` SQL via ``create_table()``.
- :class:`JsonDatatype` — lightweight namespace mapping Python
  ``DataType`` subclasses to JSON Schema type strings (``"integer"``,
  ``"string"``, etc.).
"""

import re
from typing import Any

from execsql.exceptions import ColumnError, DataTableError
from execsql.types import (
    DataType,
    DbType,
    DT_Binary,
    DT_Boolean,
    DT_Character,
    DT_Date,
    DT_Decimal,
    DT_Float,
    DT_Integer,
    DT_Long,
    DT_Text,
    DT_Time,
    DT_TimestampTZ,
    DT_Timestamp,
    DT_Varchar,
)

__all__ = [
    "Column",
    "DataTable",
    "JsonDatatype",
    "to_json_type",
]


class Column:
    """Compile data-type match statistics for a single column of imported data."""

    # Column objects are used to compile information about the data types that a set of data
    # values may match.  A Column object is intended to be used to identify the data type of a column
    # when scanning a data stream (such as a CSV file) to create a new data table.

    class Accum:
        """Accumulate match counts and length statistics for a single data type."""

        # Accumulates the count of matches for each data type, plus the maximum length if appropriate.
        def __init__(self, data_type_obj: DataType) -> None:
            """Initialise the accumulator for the given data type."""
            self.dt = data_type_obj
            self.failed = False
            self.count = 0
            self.maxlen = 0
            self.varlen = False
            self.maxprecision = None
            self.scale = None
            self.varscale = False

        def __repr__(self) -> str:
            return (
                f"Data type {self.dt.data_type_name}; failed={self.failed}; count={self.count}; maxlen={self.maxlen};"
                f" varlen={self.varlen}, precision={self.maxprecision}, scale={self.scale}, varscale={self.varscale}"
            )

        def check(self, datavalue: Any) -> None:
            """Test whether a non-null value matches this data type and update statistics."""
            # datavalue must be non-null
            if not self.failed:
                is_match = self.dt.matches(datavalue)
                if is_match:
                    self.count += 1
                    if isinstance(datavalue, str):
                        vlen = len(datavalue)
                    else:
                        # This column may turn out to have to be text, so we need the maximum length
                        # of any data value when represented as text.
                        try:
                            vlen = len(str(datavalue))
                        except Exception:
                            vlen = len(bytes(datavalue))
                    if self.maxlen > 0 and vlen != self.maxlen:
                        self.varlen = True
                    if vlen > self.maxlen:
                        self.maxlen = vlen
                    if self.dt.precision is not None and self.dt.scale is not None:
                        if self.maxprecision is None:
                            self.maxprecision = self.dt.precision
                        else:
                            self.maxprecision = max(self.dt.precision, self.maxprecision)
                        if self.scale is None:
                            self.scale = self.dt.scale
                        else:
                            if self.dt.scale != self.scale:
                                self.varscale = True
                                self.failed = True
                else:
                    self.failed = True

    def __init__(self, colname: str) -> None:
        """Create a column characteriser for the named column."""
        from execsql.exceptions import ErrInfo
        import execsql.state as _state

        if not colname:
            raise ErrInfo(
                type="error",
                other_msg="No column name is specified for a new column object to characterize a data source.",
            )
        self.name = colname.strip()
        # The rowcount for a column may not match the data rows read from the file if some data rows are short.
        self.rowcount = 0
        self.nullrows = 0
        # The list of accumulators must be in order from most specific to least specific data type.
        conf = _state.conf
        if conf.only_strings:
            self.accums = (
                self.Accum(DT_Character()),
                self.Accum(DT_Varchar()),
                self.Accum(DT_Text()),
            )
        else:
            self.accums = (
                self.Accum(DT_TimestampTZ()),
                self.Accum(DT_Timestamp()),
                self.Accum(DT_Date()),
                self.Accum(DT_Time()),
                self.Accum(DT_Boolean()),
                self.Accum(DT_Integer()),
                self.Accum(DT_Long()),
                self.Accum(DT_Decimal()),
                self.Accum(DT_Float()),
                self.Accum(DT_Character()),
                self.Accum(DT_Varchar()),
                self.Accum(DT_Text()),
                self.Accum(DT_Binary()),
            )
        self.dt_eval = False
        # self.dt is a tuple of: 0: column name; 1: data type class; 2: max length or None;
        # 3: bool indicating any null values; 4: precision or None; 5: scale or None.
        self.dt = (None, None, None, None, None, None)

    def __repr__(self) -> str:
        return f"Column({self.name!r})"

    def eval_types(self, column_value: Any) -> None:
        """Evaluate which data types the value matches and update counters."""
        # Evaluate which data type(s) the value matches, and increment the appropriate counter(s).
        import execsql.state as _state

        self.dt_eval = False
        self.rowcount += 1
        conf = _state.conf
        if column_value is not None and isinstance(column_value, str):
            if conf.trim_strings:
                column_value = column_value.strip()
            if conf.replace_newlines:
                column_value = re.sub(r"[\s\t]*[\r\n]+[\s\t]*", " ", column_value)
        if column_value is None or (
            not conf.empty_strings and isinstance(column_value, str) and len(column_value.strip()) == 0
        ):
            self.nullrows += 1
            return
        for dt in self.accums:
            dt.check(column_value)

    def column_type(self) -> tuple:
        """Return the inferred type of this column as a 6-tuple."""
        # Return the type of this column as a tuple of:
        #   column name, data type class, max length or None, bool for null values,
        #   precision or None, scale or None.
        if self.dt_eval:
            return self.dt
        sel_type = None  # Will be set to an Accum instance.
        if self.nullrows == self.rowcount:
            sel_type = self.Accum(DT_Text())
        else:
            for ac in self.accums:
                if (not ac.failed) and (ac.count == self.rowcount - self.nullrows):
                    if ac.dt.lenspec:
                        if ac.dt.varlen:
                            sel_type = ac
                            break
                        else:
                            if not ac.varlen:
                                sel_type = ac
                                break
                    else:
                        if ac.dt.precspec:
                            if ac.dt.precision is not None and ac.dt.scale is not None:
                                sel_type = ac
                                break
                        else:
                            sel_type = ac
                            break
            else:
                raise ColumnError(f"Could not determine data type for column {self.name}")
        self.dt = (
            self.name,
            sel_type.dt.__class__,
            None if not sel_type.dt.lenspec else sel_type.maxlen,
            self.nullrows > 0,
            sel_type.maxprecision,
            sel_type.scale,
        )
        self.dt_eval = True
        return self.dt


class DataTable:
    """Scan a row source and infer column types for CREATE TABLE generation."""

    def __init__(self, column_names: list[str], rowsource: Any) -> None:
        """Scan all rows from the source and infer a column type for each column."""
        import execsql.state as _state

        self.inputrows = 0  # Total number of rows in the row source.
        self.datarows = 0  # Number of non-empty rows (with data values).
        self.shortrows = 0  # Number of rows without as many data values as column names.
        self.cols: list = []  # List of Column objects.
        for n in column_names:
            self.cols.append(Column(n))
        conf = _state.conf
        # Read and evaluate columns in the rowsource until done (or until an error).
        for datarow in rowsource:
            self.inputrows += 1
            dataitems = len(datarow)
            if dataitems > 0:
                self.datarows += 1
                chkcols = len(self.cols)
                if dataitems < chkcols:
                    self.shortrows += 1
                    chkcols = len(datarow)
                else:
                    if dataitems > chkcols:
                        # If all the extra data items are null or empty string *and* conf.del_empty_cols, then OK
                        errmsg = f"Too many columns ({dataitems}) on data row {self.inputrows}"
                        if conf.del_empty_cols:
                            any_non_empty = False
                            for c in range(chkcols, dataitems):
                                column_value = datarow[c]
                                if not (
                                    column_value is None
                                    or (
                                        not conf.empty_strings
                                        and isinstance(column_value, str)
                                        and len(column_value.strip()) == 0
                                    )
                                ):
                                    any_non_empty = True
                                    break
                            if any_non_empty:
                                raise DataTableError(errmsg)
                        else:
                            raise DataTableError(errmsg)
                for i in range(chkcols):
                    self.cols[i].eval_types(datarow[i])
        for col in self.cols:
            col.column_type()

    def __repr__(self) -> str:
        return f"DataTable({[col.name for col in self.cols]!r}, rowsource)"

    def column_declarations(self, database_type: DbType) -> list[str]:
        """Return a list of SQL column-declaration strings for the given DBMS."""
        # Returns a list of column specifications.
        spec = []
        for col in self.cols:
            spec.append(database_type.column_spec(*col.column_type()))
        return spec

    def create_table(
        self,
        database_type: DbType,
        schemaname: str | None,
        tablename: str,
        pretty: bool = False,
    ) -> str:
        """Generate a CREATE TABLE statement for the given DBMS and table name."""
        tb = (
            f"{database_type.quoted(schemaname)}.{database_type.quoted(tablename)}"
            if schemaname
            else database_type.quoted(tablename)
        )
        if pretty:
            return "CREATE TABLE {} (\n    {}\n    );".format(
                tb,
                ",\n    ".join(self.column_declarations(database_type)),
            )
        else:
            return "CREATE TABLE {} ( {} );".format(tb, ", ".join(self.column_declarations(database_type)))


class JsonDatatype:
    """Namespace mapping Python DataType subclasses to JSON Schema type strings."""

    def __init__(self) -> None:
        """Create an empty JsonDatatype namespace instance."""
        pass


JsonDatatype.any = "any"
JsonDatatype.integer = "integer"
JsonDatatype.string = "string"
JsonDatatype.date = "date"
JsonDatatype.datetime = "datetime"
JsonDatatype.time = "time"
JsonDatatype.number = "number"
JsonDatatype.boolean = "boolean"

# Types without a JSON type equivalent are converted
# to strings via the "default=str" argument of 'json.dumps()'.
to_json_type = {
    DT_TimestampTZ: JsonDatatype.string,
    DT_Timestamp: JsonDatatype.datetime,
    DT_Date: JsonDatatype.date,
    DT_Time: JsonDatatype.time,
    DT_Integer: JsonDatatype.integer,
    DT_Long: JsonDatatype.integer,
    DT_Float: JsonDatatype.number,
    DT_Decimal: JsonDatatype.number,
    DT_Boolean: JsonDatatype.boolean,
    DT_Character: JsonDatatype.string,
    DT_Varchar: JsonDatatype.string,
    DT_Text: JsonDatatype.string,
    DT_Binary: JsonDatatype.string,
}
