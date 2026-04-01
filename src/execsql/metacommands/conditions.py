from __future__ import annotations

"""
Conditional test handler functions for execsql.

Implements all ``xf_*`` functions — the conditional test predicates used
by IF/ELSEIF expressions — and the ``x_if``, ``x_elseif``, ``x_else``,
and ``x_endif`` imperative handlers that manage the IF-nesting stack.

Examples of conditional tests defined here: ``xf_tableexists``,
``xf_fileexists``, ``xf_equals``, ``xf_contains``, ``xf_startswith``,
``xf_greaterthan``, etc., along with all their quoting variants generated
at registration time.
"""

import os
from execsql.exceptions import ErrInfo
import time
from pathlib import Path
from typing import Any
from collections.abc import Callable

import execsql.state as _state
from execsql.utils.regex import ins_fn_rxs
from execsql.parser import CondParser
from execsql.script import MetaCommandList
from execsql.types import DT_Boolean, DT_Date, DT_Timestamp, DT_TimestampTZ
from execsql.utils.datetime import parse_datetime
from execsql.utils.errors import exception_desc
from execsql.utils.gui import gui_console_isrunning
from execsql.utils.strings import unquoted


def xf_contains(**kwargs: Any) -> bool:
    s1 = kwargs["string1"]
    s2 = kwargs["string2"]
    if kwargs["ignorecase"] and kwargs["ignorecase"].lower() == "i":
        s1 = s1.lower()
        s2 = s2.lower()
    return s2 in s1


def xf_startswith(**kwargs: Any) -> bool:
    s1 = kwargs["string1"]
    s2 = kwargs["string2"]
    if kwargs["ignorecase"] and kwargs["ignorecase"].lower() == "i":
        s1 = s1.lower()
        s2 = s2.lower()
    return s1[: len(s2)] == s2


def xf_endswith(**kwargs: Any) -> bool:
    s1 = kwargs["string1"]
    s2 = kwargs["string2"]
    if kwargs["ignorecase"] and kwargs["ignorecase"].lower() == "i":
        s1 = s1.lower()
        s2 = s2.lower()
    return s1[-len(s2) :] == s2


def xf_hasrows(**kwargs: Any) -> bool:
    queryname = kwargs["queryname"]
    sql = f"select count(*) from {queryname};"
    try:
        hdrs, rec = _state.dbs.current().select_data(sql)
    except ErrInfo:
        raise
    except Exception as e:
        raise ErrInfo("db", sql, exception_msg=exception_desc()) from e
    nrows = rec[0][0]
    return nrows > 0


def _row_count(queryname: str, sql_context: str, metacommandline: str) -> int:
    """Return the number of rows in *queryname*, raising ErrInfo on failure.

    Args:
        queryname: Table or view name to count rows in.
        sql_context: The SQL string to include in error messages.
        metacommandline: The full metacommand line for error context.

    Returns:
        Integer row count.

    Raises:
        ErrInfo: If the query fails or the result is not numeric.
    """
    sql = f"select count(*) from {queryname};"
    try:
        _hdrs, rec = _state.dbs.current().select_data(sql)
    except ErrInfo:
        raise
    except Exception as e:
        raise ErrInfo("db", sql, exception_msg=exception_desc()) from e
    try:
        return int(rec[0][0])
    except (IndexError, TypeError, ValueError) as e:
        raise ErrInfo(
            type="cmd",
            command_text=metacommandline,
            other_msg=f"Could not read row count for {queryname}.",
        ) from e


def _parse_row_count_n(raw: str, metacommandline: str) -> int:
    """Parse and return the numeric threshold N from the matched group.

    Args:
        raw: The raw string captured by the regex group (``n``).
        metacommandline: The full metacommand line for error context.

    Returns:
        Integer value of *raw*.

    Raises:
        ErrInfo: If *raw* cannot be parsed as an integer.
    """
    try:
        return int(raw.strip())
    except (ValueError, TypeError) as e:
        raise ErrInfo(
            type="cmd",
            command_text=metacommandline,
            other_msg=f"ROW_COUNT threshold must be an integer; got {raw!r}.",
        ) from e


def xf_row_count_gt(**kwargs: Any) -> bool:
    """Return True if the row count of *queryname* is strictly greater than N.

    Args:
        **kwargs: Named groups from the regex match, plus ``metacommandline``.
            Required keys: ``queryname``, ``n``.

    Returns:
        True if ``count(*) > N``.
    """
    queryname = kwargs["queryname"]
    mcl = kwargs["metacommandline"]
    n = _parse_row_count_n(kwargs["n"], mcl)
    return _row_count(queryname, f"select count(*) from {queryname};", mcl) > n


def xf_row_count_gte(**kwargs: Any) -> bool:
    """Return True if the row count of *queryname* is greater than or equal to N.

    Args:
        **kwargs: Named groups from the regex match, plus ``metacommandline``.
            Required keys: ``queryname``, ``n``.

    Returns:
        True if ``count(*) >= N``.
    """
    queryname = kwargs["queryname"]
    mcl = kwargs["metacommandline"]
    n = _parse_row_count_n(kwargs["n"], mcl)
    return _row_count(queryname, f"select count(*) from {queryname};", mcl) >= n


def xf_row_count_eq(**kwargs: Any) -> bool:
    """Return True if the row count of *queryname* equals N exactly.

    Args:
        **kwargs: Named groups from the regex match, plus ``metacommandline``.
            Required keys: ``queryname``, ``n``.

    Returns:
        True if ``count(*) == N``.
    """
    queryname = kwargs["queryname"]
    mcl = kwargs["metacommandline"]
    n = _parse_row_count_n(kwargs["n"], mcl)
    return _row_count(queryname, f"select count(*) from {queryname};", mcl) == n


def xf_row_count_lt(**kwargs: Any) -> bool:
    """Return True if the row count of *queryname* is strictly less than N.

    Args:
        **kwargs: Named groups from the regex match, plus ``metacommandline``.
            Required keys: ``queryname``, ``n``.

    Returns:
        True if ``count(*) < N``.
    """
    queryname = kwargs["queryname"]
    mcl = kwargs["metacommandline"]
    n = _parse_row_count_n(kwargs["n"], mcl)
    return _row_count(queryname, f"select count(*) from {queryname};", mcl) < n


def xf_sqlerror(**kwargs: Any) -> bool:
    return _state.status.sql_error


def xf_dialogcanceled(**kwargs: Any) -> bool:
    return _state.status.dialog_canceled


def xf_fileexists(**kwargs: Any) -> bool:
    filename = kwargs["filename"]
    return Path(filename.strip()).is_file()


def xf_direxists(**kwargs: Any) -> bool:
    dirname = kwargs["dirname"]
    return Path(dirname.strip()).is_dir()


def xf_schemaexists(**kwargs: Any) -> bool:
    schemaname = kwargs["schema"]
    return _state.dbs.current().schema_exists(schemaname)


def xf_tableexists(**kwargs: Any) -> bool:
    schemaname = kwargs["schema"]
    tablename = kwargs["tablename"]
    return _state.dbs.current().table_exists(tablename.strip(), schemaname)


def xf_roleexists(**kwargs: Any) -> bool:
    rolename = kwargs["role"]
    return _state.dbs.current().role_exists(rolename)


def xf_sub_defined(**kwargs: Any) -> bool:
    varname = kwargs["match_str"]
    if varname[0] not in ("~", "#"):
        subvarset = _state.subvars
    elif varname[0] == "~":
        subvarset = _state.commandliststack[-1].localvars
    else:
        subvarset = _state.commandliststack[-1].paramvals
    return subvarset.sub_exists(varname) if subvarset else False


def xf_sub_empty(**kwargs: Any) -> bool:
    varname = kwargs["match_str"]
    if varname[0] not in ("~", "#"):
        subvarset = _state.subvars
    elif varname[0] == "~":
        subvarset = _state.commandliststack[-1].localvars
    else:
        subvarset = _state.commandliststack[-1].paramvals
    if not subvarset.sub_exists(varname):
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Unrecognized substitution variable name: {varname}",
        )
    return subvarset.varvalue(varname) == ""


def xf_script_exists(**kwargs: Any) -> bool:
    script_id = kwargs["script_id"].lower()
    return script_id in _state.savedscripts


def xf_equals(**kwargs: Any) -> bool:
    import unicodedata

    s1 = unicodedata.normalize("NFC", kwargs["string1"]).lower().strip('"')
    s2 = unicodedata.normalize("NFC", kwargs["string2"]).lower().strip('"')
    converters = (
        int,
        float,
        DT_Timestamp().from_data,
        DT_TimestampTZ().from_data,
        DT_Date().from_data,
        DT_Boolean().from_data,
    )
    for convf in converters:
        try:
            v1 = convf(s1)
            v2 = convf(s2)
        except Exception:
            continue
        are_eq = v1 == v2
        if are_eq:
            break
    else:
        are_eq = s1 == s2
    return are_eq


def xf_identical(**kwargs: Any) -> bool:
    s1 = kwargs["string1"].strip('"')
    s2 = kwargs["string2"].strip('"')
    return s1 == s2


def xf_isnull(**kwargs: Any) -> bool:
    item = kwargs["item"].strip().strip('"')
    return item == ""


def xf_iszero(**kwargs: Any) -> bool:
    val = kwargs["value"].strip()
    try:
        v = float(val)
    except Exception as e:
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"The value {{{val}}} is not numeric.",
        ) from e
    return v == 0


def xf_isgt(**kwargs: Any) -> bool:
    val1 = kwargs["value1"].strip()
    val2 = kwargs["value2"].strip()
    try:
        v1 = float(val1)
        v2 = float(val2)
    except Exception as e:
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Values {{{val1}}} and {{{val2}}} are not both numeric.",
        ) from e
    return v1 > v2


def xf_isgte(**kwargs: Any) -> bool:
    val1 = kwargs["value1"].strip()
    val2 = kwargs["value2"].strip()
    try:
        v1 = float(val1)
        v2 = float(val2)
    except Exception as e:
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Values {{{val1}}} and {{{val2}}} are not both numeric.",
        ) from e
    return v1 >= v2


def xf_boolliteral(**kwargs: Any) -> bool:
    return unquoted(kwargs["value"].strip()).lower() in ("true", "yes", "1")


def xf_istrue(**kwargs: Any) -> bool:
    return unquoted(kwargs["value"].strip()).lower() in ("yes", "y", "true", "t", "1")


def xf_dbms(**kwargs: Any) -> bool:
    dbms = kwargs["dbms"]
    return _state.dbs.current().type.dbms_id.lower() == dbms.strip().lower()


def xf_dbname(**kwargs: Any) -> bool:
    dbname = kwargs["dbname"]
    return _state.dbs.current().name().lower() == dbname.strip().lower()


def xf_viewexists(**kwargs: Any) -> bool:
    viewname = kwargs["viewname"]
    return _state.dbs.current().view_exists(viewname.strip())


def xf_columnexists(**kwargs: Any) -> bool:
    tablename = kwargs["tablename"]
    schemaname = kwargs["schema"]
    columnname = kwargs["columnname"]
    return _state.dbs.current().column_exists(tablename.strip(), columnname.strip(), schemaname)


def xf_aliasdefined(**kwargs: Any) -> bool:
    alias = kwargs["alias"]
    return alias in _state.dbs.aliases()


def xf_metacommanderror(**kwargs: Any) -> bool:
    return _state.status.metacommand_error


def xf_console(**kwargs: Any) -> bool:
    return gui_console_isrunning()


def xf_newer_file(**kwargs: Any) -> bool:
    file1 = kwargs["file1"]
    file2 = kwargs["file2"]
    if not Path(file1).exists():
        raise ErrInfo(type="cmd", other_msg=f"File {file1} does not exist.")
    if not Path(file2).exists():
        raise ErrInfo(type="cmd", other_msg=f"File {file2} does not exist.")
    return os.stat(file1).st_mtime > os.stat(file2).st_mtime


def xf_newer_date(**kwargs: Any) -> bool:
    file1 = kwargs["file1"]
    datestr = unquoted(kwargs["datestr"])
    if not Path(file1).exists():
        raise ErrInfo(type="cmd", other_msg=f"File {file1} does not exist.")
    dt_value = parse_datetime(datestr)
    if not dt_value:
        raise ErrInfo(type="cmd", other_msg=f"{datestr} can't be interpreted as a date/time.")
    return os.stat(file1).st_mtime > time.mktime(dt_value.timetuple())


def build_conditional_table() -> Any:
    """Construct and return the conditional predicate dispatch table."""
    mcl = MetaCommandList()

    # CONTAINS
    mcl.add(
        r"^\s*CONTAINS\s*\(\s*(?P<string1>[^ )]+)\s*,\s*(?P<string2>[^ )]+)(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_contains,
        description="CONTAINS",
        category="condition",
    )
    mcl.add(
        r'^\s*CONTAINS\s*\(\s*"(?P<string1>[^"]+)"\s*,\s*(?P<string2>[^ )]+)(?:\s*,\s*(?P<ignorecase>I))?\s*\)',
        xf_contains,
    )
    mcl.add(
        r'^\s*CONTAINS\s*\(\s*(?P<string1>[^ )]+)\s*,\s*"(?P<string2>[^"]+)"(?:\s*,\s*(?P<ignorecase>I))?\s*\)',
        xf_contains,
    )
    mcl.add(
        r"^\s*CONTAINS\s*\(\s*(?P<string1>[^ )]+)\s*,\s*'(?P<string2>[^']+)'\s*(?:\s*,\s*(?P<ignorecase>I))?\)",
        xf_contains,
    )
    mcl.add(
        r"^\s*CONTAINS\s*\(\s*(?P<string1>[^ )]+)\s*,\s*`(?P<string2>[^`]+)`(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_contains,
    )
    mcl.add(
        r"^\s*CONTAINS\s*\(\s*`(?P<string1>[^`]+)`\s*,\s*(?P<string2>[^ )]+)(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_contains,
    )
    mcl.add(
        r"^\s*CONTAINS\s*\(\s*'(?P<string1>[^']+)'\s*,\s*(?P<string2>[^ )]+)\s*(?:\s*,\s*(?P<ignorecase>I))?\)",
        xf_contains,
    )
    mcl.add(
        r'^\s*CONTAINS\s*\(\s*"(?P<string1>[^"]+)"\s*,\s*"(?P<string2>[^"]+)"(?:\s*,\s*(?P<ignorecase>I))?\s*\)',
        xf_contains,
    )
    mcl.add(
        r"^\s*CONTAINS\s*\(\s*'(?P<string1>[^']+)'\s*,\s*'(?P<string2>[^']+)'(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_contains,
    )
    mcl.add(
        r"^\s*CONTAINS\s*\(\s*'(?P<string1>[^']+)'\s*,\s*\"(?P<string2>[^\"]+)\"(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_contains,
    )
    mcl.add(
        r"^\s*CONTAINS\s*\(\s*\"(?P<string1>[^\"]+)\"\s*,\s*'(?P<string2>[^']+)'(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_contains,
    )
    mcl.add(
        r"^\s*CONTAINS\s*\(\s*`(?P<string1>[^`]+)`\s*,\s*`(?P<string2>[^`]+)`(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_contains,
    )
    mcl.add(
        r'^\s*CONTAINS\s*\(\s*`(?P<string1>[^`]+)`\s*,\s*"(?P<string2>[^"]+)"(?:\s*,\s*(?P<ignorecase>I))?\s*\)',
        xf_contains,
    )
    mcl.add(
        r'^\s*CONTAINS\s*\(\s*"(?P<string1>[^"]+)"\s*,\s*`(?P<string2>[^`]+)`(?:\s*,\s*(?P<ignorecase>I))?\s*\)',
        xf_contains,
    )
    mcl.add(
        r"^\s*CONTAINS\s*\(\s*`(?P<string1>[^`]+)`\s*,\s*'(?P<string2>[^']+)'(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_contains,
    )
    mcl.add(
        r"^\s*CONTAINS\s*\(\s*'(?P<string1>[^']+)'\s*,\s*`(?P<string2>[^`]+)`(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_contains,
    )

    # STARTS_WITH
    mcl.add(
        r"^\s*STARTS_WITH\s*\(\s*(?P<string1>[^ )]+)\s*,\s*(?P<string2>[^ )]+)(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_startswith,
        description="STARTS_WITH",
        category="condition",
    )
    mcl.add(
        r'^\s*STARTS_WITH\s*\(\s*"(?P<string1>[^"]+)"\s*,\s*(?P<string2>[^ )]+)(?:\s*,\s*(?P<ignorecase>I))?\s*\)',
        xf_startswith,
    )
    mcl.add(
        r'^\s*STARTS_WITH\s*\(\s*(?P<string1>[^ )]+)\s*,\s*"(?P<string2>[^"]+)"(?:\s*,\s*(?P<ignorecase>I))?\s*\)',
        xf_startswith,
    )
    mcl.add(
        r"^\s*STARTS_WITH\s*\(\s*(?P<string1>[^ )]+)\s*,\s*'(?P<string2>[^']+)'\s*(?:\s*,\s*(?P<ignorecase>I))?\)",
        xf_startswith,
    )
    mcl.add(
        r"^\s*STARTS_WITH\s*\(\s*(?P<string1>[^ )]+)\s*,\s*`(?P<string2>[^`]+)`(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_startswith,
    )
    mcl.add(
        r"^\s*STARTS_WITH\s*\(\s*`(?P<string1>[^`]+)`\s*,\s*(?P<string2>[^ )]+)(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_startswith,
    )
    mcl.add(
        r"^\s*STARTS_WITH\s*\(\s*'(?P<string1>[^']+)'\s*,\s*(?P<string2>[^ )]+)\s*(?:\s*,\s*(?P<ignorecase>I))?\)",
        xf_startswith,
    )
    mcl.add(
        r'^\s*STARTS_WITH\s*\(\s*"(?P<string1>[^"]+)"\s*,\s*"(?P<string2>[^"]+)"(?:\s*,\s*(?P<ignorecase>I))?\s*\)',
        xf_startswith,
    )
    mcl.add(
        r"^\s*STARTS_WITH\s*\(\s*'(?P<string1>[^']+)'\s*,\s*'(?P<string2>[^']+)'(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_startswith,
    )
    mcl.add(
        r"^\s*STARTS_WITH\s*\(\s*'(?P<string1>[^']+)'\s*,\s*\"(?P<string2>[^\"]+)\"(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_startswith,
    )
    mcl.add(
        r"^\s*STARTS_WITH\s*\(\s*\"(?P<string1>[^\"]+)\"\s*,\s*'(?P<string2>[^']+)'(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_startswith,
    )
    mcl.add(
        r"^\s*STARTS_WITH\s*\(\s*`(?P<string1>[^`]+)`\s*,\s*`(?P<string2>[^`]+)`(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_startswith,
    )
    mcl.add(
        r'^\s*STARTS_WITH\s*\(\s*`(?P<string1>[^`]+)`\s*,\s*"(?P<string2>[^"]+)"(?:\s*,\s*(?P<ignorecase>I))?\s*\)',
        xf_startswith,
    )
    mcl.add(
        r'^\s*STARTS_WITH\s*\(\s*"(?P<string1>[^"]+)"\s*,\s*`(?P<string2>[^`]+)`(?:\s*,\s*(?P<ignorecase>I))?\s*\)',
        xf_startswith,
    )
    mcl.add(
        r"^\s*STARTS_WITH\s*\(\s*`(?P<string1>[^`]+)`\s*,\s*'(?P<string2>[^']+)'(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_startswith,
    )
    mcl.add(
        r"^\s*STARTS_WITH\s*\(\s*'(?P<string1>[^']+)'\s*,\s*`(?P<string2>[^`]+)`(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_startswith,
    )

    # ENDS_WITH
    mcl.add(
        r"^\s*ENDS_WITH\s*\(\s*(?P<string1>[^ )]+)\s*,\s*(?P<string2>[^ )]+)(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_endswith,
        description="ENDS_WITH",
        category="condition",
    )
    mcl.add(
        r'^\s*ENDS_WITH\s*\(\s*"(?P<string1>[^"]+)"\s*,\s*(?P<string2>[^ )]+)(?:\s*,\s*(?P<ignorecase>I))?\s*\)',
        xf_endswith,
    )
    mcl.add(
        r'^\s*ENDS_WITH\s*\(\s*(?P<string1>[^ )]+)\s*,\s*"(?P<string2>[^"]+)"(?:\s*,\s*(?P<ignorecase>I))?\s*\)',
        xf_endswith,
    )
    mcl.add(
        r"^\s*ENDS_WITH\s*\(\s*(?P<string1>[^ )]+)\s*,\s*'(?P<string2>[^']+)'\s*(?:\s*,\s*(?P<ignorecase>I))?\)",
        xf_endswith,
    )
    mcl.add(
        r"^\s*ENDS_WITH\s*\(\s*(?P<string1>[^ )]+)\s*,\s*`(?P<string2>[^`]+)`(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_endswith,
    )
    mcl.add(
        r"^\s*ENDS_WITH\s*\(\s*`(?P<string1>[^`]+)`\s*,\s*(?P<string2>[^ )]+)(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_endswith,
    )
    mcl.add(
        r"^\s*ENDS_WITH\s*\(\s*'(?P<string1>[^']+)'\s*,\s*(?P<string2>[^ )]+)\s*(?:\s*,\s*(?P<ignorecase>I))?\)",
        xf_endswith,
    )
    mcl.add(
        r'^\s*ENDS_WITH\s*\(\s*"(?P<string1>[^"]+)"\s*,\s*"(?P<string2>[^"]+)"(?:\s*,\s*(?P<ignorecase>I))?\s*\)',
        xf_endswith,
    )
    mcl.add(
        r"^\s*ENDS_WITH\s*\(\s*'(?P<string1>[^']+)'\s*,\s*'(?P<string2>[^']+)'(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_endswith,
    )
    mcl.add(
        r"^\s*ENDS_WITH\s*\(\s*'(?P<string1>[^']+)'\s*,\s*\"(?P<string2>[^\"]+)\"(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_endswith,
    )
    mcl.add(
        r"^\s*ENDS_WITH\s*\(\s*\"(?P<string1>[^\"]+)\"\s*,\s*'(?P<string2>[^']+)'(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_endswith,
    )
    mcl.add(
        r"^\s*ENDS_WITH\s*\(\s*`(?P<string1>[^`]+)`\s*,\s*`(?P<string2>[^`]+)`(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_endswith,
    )
    mcl.add(
        r'^\s*ENDS_WITH\s*\(\s*`(?P<string1>[^`]+)`\s*,\s*"(?P<string2>[^"]+)"(?:\s*,\s*(?P<ignorecase>I))?\s*\)',
        xf_endswith,
    )
    mcl.add(
        r'^\s*ENDS_WITH\s*\(\s*"(?P<string1>[^"]+)"\s*,\s*`(?P<string2>[^`]+)`(?:\s*,\s*(?P<ignorecase>I))?\s*\)',
        xf_endswith,
    )
    mcl.add(
        r"^\s*ENDS_WITH\s*\(\s*`(?P<string1>[^`]+)`\s*,\s*'(?P<string2>[^']+)'(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_endswith,
    )
    mcl.add(
        r"^\s*ENDS_WITH\s*\(\s*'(?P<string1>[^']+)'\s*,\s*`(?P<string2>[^`]+)`(?:\s*,\s*(?P<ignorecase>I))?\s*\)",
        xf_endswith,
    )

    # HASROWS / HAS_ROWS
    mcl.add(r"^\s*HASROWS\((?P<queryname>[^)]+)\)", xf_hasrows, description="HASROWS", category="condition")
    mcl.add(r"^\s*HAS_ROWS\((?P<queryname>[^)]+)\)", xf_hasrows)

    # ROW_COUNT comparisons — ROW_COUNT_GT/GTE/EQ/LT(table, N)
    # Table name: unquoted, double-quoted, or single-quoted.  N: integer literal.
    _rc_table = r"(?P<queryname>[A-Za-z0-9_.\"'\[\]]+)"
    _rc_n = r"(?P<n>\d+)"
    _rc_sep = r"\s*,\s*"
    mcl.add(
        rf"^\s*ROW_COUNT_GT\s*\(\s*{_rc_table}{_rc_sep}{_rc_n}\s*\)",
        xf_row_count_gt,
        description="ROW_COUNT_GT",
        category="condition",
    )
    mcl.add(
        rf"^\s*ROW_COUNT_GTE\s*\(\s*{_rc_table}{_rc_sep}{_rc_n}\s*\)",
        xf_row_count_gte,
        description="ROW_COUNT_GTE",
        category="condition",
    )
    mcl.add(
        rf"^\s*ROW_COUNT_EQ\s*\(\s*{_rc_table}{_rc_sep}{_rc_n}\s*\)",
        xf_row_count_eq,
        description="ROW_COUNT_EQ",
        category="condition",
    )
    mcl.add(
        rf"^\s*ROW_COUNT_LT\s*\(\s*{_rc_table}{_rc_sep}{_rc_n}\s*\)",
        xf_row_count_lt,
        description="ROW_COUNT_LT",
        category="condition",
    )

    # Status predicates
    mcl.add(r"^\s*sql_error\(\s*\)", xf_sqlerror, description="SQL_ERROR", category="condition")
    mcl.add(r"^\s*dialog_canceled\(\s*\)", xf_dialogcanceled, description="DIALOG_CANCELED", category="condition")
    mcl.add(r"^\s*metacommand_error\(\s*\)", xf_metacommanderror, description="METACOMMAND_ERROR", category="condition")
    mcl.add(r"^\s*CONSOLE_ON", xf_console, description="CONSOLE_ON", category="condition")

    # FILE / DIRECTORY
    mcl.add(ins_fn_rxs(r"^FILE_EXISTS\(\s*", r"\)"), xf_fileexists, description="FILE_EXISTS", category="condition")
    mcl.add(
        r'^DIRECTORY_EXISTS\(\s*("?)(?P<dirname>[^")]+)\1\)',
        xf_direxists,
        description="DIRECTORY_EXISTS",
        category="condition",
    )

    # Database object existence
    mcl.add(
        (
            r"^SCHEMA_EXISTS\(\s*(?P<schema>[A-Za-z0-9_\-\: ]+)\s*\)",
            r'^SCHEMA_EXISTS\(\s*"(?P<schema>[A-Za-z0-9_\-\: ]+)"\s*\)',
        ),
        xf_schemaexists,
        description="SCHEMA_EXISTS",
        category="condition",
    )
    mcl.add(
        (
            r"^TABLE_EXISTS\(\s*(?:(?P<schema>[A-Za-z0-9_\-\/\: ]+)\.)?(?P<tablename>[A-Za-z0-9_\-\/\: ]+)\)",
            r"^TABLE_EXISTS\(\s*(?:\[(?P<schema>[A-Za-z0-9_\-\/\: ]+)\]\.)?\[(?P<tablename>[A-Za-z0-9_\-\/\: ]+)\]\)",
            r'^TABLE_EXISTS\(\s*(?:"(?P<schema>[A-Za-z0-9_\-\/\: ]+)"\.)?"(?P<tablename>[A-Za-z0-9_\-\/\: ]+)"\)',
            r"^TABLE_EXISTS\(\s*(?:(?P<schema>[A-Za-z0-9_\-\/]+)\.)?(?P<tablename>[A-Za-z0-9_\-\/]+)\)",
        ),
        xf_tableexists,
        description="TABLE_EXISTS",
        category="condition",
    )
    mcl.add(
        (
            r"^ROLE_EXISTS\(\s*(?P<role>[A-Za-z0-9_\-\:\$ ]+)\s*\)",
            r'^ROLE_EXISTS\(\s*"(?P<role>[A-Za-z0-9_\-\:\$ ]+)"\s*\)',
        ),
        xf_roleexists,
        description="ROLE_EXISTS",
        category="condition",
    )
    mcl.add(
        r'^\s*VIEW_EXISTS\(\s*("?)(?P<viewname>[^")]+)\1\)',
        xf_viewexists,
        description="VIEW_EXISTS",
        category="condition",
    )
    mcl.add(
        (
            r"^COLUMN_EXISTS\(\s*(?P<columnname>[A-Za-z0-9_\-\:]+)\s+IN\s+(?:(?P<schema>[A-Za-z0-9_\-\: ]+)\.)?(?P<tablename>[A-Za-z0-9_\-\: ]+)\)",
            r"^COLUMN_EXISTS\(\s*(?P<columnname>[A-Za-z0-9_\-\:]+)\s+IN\s+(?:\[(?P<schema>[A-Za-z0-9_\-\: ]+)\]\.)?\[(?P<tablename>[A-Za-z0-9_\-\: ]+)\]\)",
            r'^COLUMN_EXISTS\(\s*(?P<columnname>[A-Za-z0-9_\-\:]+)\s+IN\s+(?:"(?P<schema>[A-Za-z0-9_\-\: ]+)"\.)?"(?P<tablename>[A-Za-z0-9_\-\: ]+)"\)',
            r'^COLUMN_EXISTS\(\s*"(?P<columnname>[A-Za-z0-9_\-\: ]+)"\s+IN\s+(?:(?P<schema>[A-Za-z0-9_\-\: ]+)\.)?(?P<tablename>[A-Za-z0-9_\-\: ]+)\)',
            r'^COLUMN_EXISTS\(\s*"(?P<columnname>[A-Za-z0-9_\-\: ]+)"\s+IN\s+(?:\[(?P<schema>[A-Za-z0-9_\-\: ]+)\]\.)?\[(?P<tablename>[A-Za-z0-9_\-\: ]+)\]\)',
            r'^COLUMN_EXISTS\(\s*"(?P<columnname>[A-Za-z0-9_\-\: ]+)"\s+IN\s+(?:"(?P<schema>[A-Za-z0-9_\-\: ]+)"\.)?"(?P<tablename>[A-Za-z0-9_\-\: ]+)"\)',
        ),
        xf_columnexists,
        description="COLUMN_EXISTS",
        category="condition",
    )
    mcl.add(
        r"^\s*ALIAS_DEFINED\s*\(\s*(?P<alias>\w+)\s*\)",
        xf_aliasdefined,
        description="ALIAS_DEFINED",
        category="condition",
    )

    # Substitution variable predicates
    mcl.add(
        r"^SUB_DEFINED\s*\(\s*(?P<match_str>[\$&@~#]?\w+)\s*\)",
        xf_sub_defined,
        description="SUB_DEFINED",
        category="condition",
    )
    mcl.add(
        r"^SUB_EMPTY\s*\(\s*(?P<match_str>[\$&@~#]?\w+)\s*\)",
        xf_sub_empty,
        description="SUB_EMPTY",
        category="condition",
    )
    mcl.add(
        r"^\s*SCRIPT_EXISTS\s*\(\s*(?P<script_id>\w+)\s*\)",
        xf_script_exists,
        description="SCRIPT_EXISTS",
        category="condition",
    )

    # Comparison predicates
    mcl.add(
        r"^\s*EQUAL(S)?\s*\(\s*(?P<string1>[^ )]+)\s*,\s*(?P<string2>[^ )]+)\s*\)",
        xf_equals,
        description="EQUAL",
        category="condition",
    )
    mcl.add(r'^\s*EQUAL(S)?\s*\(\s*"(?P<string1>[^"]+)"\s*,\s*(?P<string2>[^ )]+)\s*\)', xf_equals)
    mcl.add(r'^\s*EQUAL(S)?\s*\(\s*(?P<string1>[^ )]+)\s*,\s*"(?P<string2>[^"]+)"\s*\)', xf_equals)
    mcl.add(r'^\s*EQUAL(S)?\s*\(\s*"(?P<string1>[^"]+)"\s*,\s*"(?P<string2>[^"]+)"\s*\)', xf_equals)
    mcl.add(
        r"^\s*IDENTICAL\s*\(\s*(?P<string1>[^ ,)]+)\s*,\s*(?P<string2>[^ )]+)\s*\)",
        xf_identical,
        description="IDENTICAL",
        category="condition",
    )
    mcl.add(r'^\s*IDENTICAL\s*\(\s*"(?P<string1>[^"]+)"\s*,\s*(?P<string2>[^ )]+)\s*\)', xf_identical)
    mcl.add(r'^\s*IDENTICAL\s*\(\s*(?P<string1>[^ ,]+)\s*,\s*"(?P<string2>[^"]+)"\s*\)', xf_identical)
    mcl.add(r'^\s*IDENTICAL\s*\(\s*"(?P<string1>[^"]+)"\s*,\s*"(?P<string2>[^"]+)"\s*\)', xf_identical)
    mcl.add(r'^\s*IS_NULL\(\s*(?P<item>"[^"]*")\s*\)', xf_isnull, description="IS_NULL", category="condition")
    mcl.add(r"^\s*IS_ZERO\(\s*(?P<value>[^)]*)\s*\)", xf_iszero, description="IS_ZERO", category="condition")
    mcl.add(
        r"^\s*IS_GT\(\s*(?P<value1>[^)]*)\s*,\s*(?P<value2>[^)]*)\s*\)",
        xf_isgt,
        description="IS_GT",
        category="condition",
    )
    mcl.add(
        r"^\s*IS_GTE\(\s*(?P<value1>[^)]*)\s*,\s*(?P<value2>[^)]*)\s*\)",
        xf_isgte,
        description="IS_GTE",
        category="condition",
    )
    mcl.add(r"^\s*IS_TRUE\(\s*(?P<value>[^)]*)\s*\)", xf_istrue, description="IS_TRUE", category="condition")

    # Boolean literals
    mcl.add(
        (
            r"^\s*(?P<value>1)\s*",
            r'^\s*(?P<value>"1")\s*',
            r"^\s*(?P<value>0)\s*",
            r'^\s*(?P<value>"0")\s*',
            r"^\s*(?P<value>Yes)\s*",
            r'^\s*(?P<value>"Yes")\s*',
            r"^\s*(?P<value>No)\s*",
            r'^\s*(?P<value>"No")\s*',
            r'^\s*(?P<value>"False")\s*',
            r"^\s*(?P<value>False)\s*",
            r'^\s*(?P<value>"True")\s*',
            r"^\s*(?P<value>True)\s*",
        ),
        xf_boolliteral,
        description="IS_TRUE",
        category="condition",
    )

    # Database type / name
    mcl.add(
        (
            r"^\s*DBMS\(\s*(?P<dbms>[A-Z0-9_\-\(\/\\\. ]+)\s*\)",
            r'^\s*DBMS\(\s*"(?P<dbms>[A-Z0-9_\-\(\)\/\\\. ]+)"\s*\)',
        ),
        xf_dbms,
        description="DBMS",
        category="condition",
    )
    mcl.add(
        (
            r"^\s*DATABASE_NAME\(\s*(?P<dbname>[A-Z0-9_;\-\(\/\\\. ]+)\s*\)",
            r'^\s*DATABASE_NAME\(\s*"(?P<dbname>[A-Z0-9_;\-\(\)\/\\\. ]+)"\s*\)',
        ),
        xf_dbname,
        description="DATABASE_NAME",
        category="condition",
    )

    # File modification time comparisons
    mcl.add(
        ins_fn_rxs(
            r"^\s*NEWER_FILE\s*\(\s*",
            ins_fn_rxs(r"\s*,\s*", r"\s*\)", symbolicname="file2"),
            symbolicname="file1",
        ),
        xf_newer_file,
        description="NEWER_FILE",
        category="condition",
    )
    mcl.add(
        ins_fn_rxs(
            r"^\s*NEWER_DATE\s*\(\s*",
            r"\s*,\s*(?P<datestr>[^)]+)\s*\)",
            symbolicname="file1",
        ),
        xf_newer_date,
        description="NEWER_DATE",
        category="condition",
    )

    return mcl


CONDITIONAL_TABLE = build_conditional_table()


def xcmd_test(teststr: str) -> bool:
    result = CondParser(teststr).parse().eval()
    if result is not None:
        return result
    else:
        raise ErrInfo(type="cmd", command_text=teststr, other_msg="Unrecognized conditional")


def file_size_date(filename: str) -> tuple[int, str]:
    """Returns the file size and date (as string) of the given file."""
    s_file = str(Path(filename).resolve())
    f_stat = os.stat(s_file)
    return f_stat.st_size, time.strftime("%Y-%m-%d %H:%M", time.gmtime(f_stat.st_mtime))


def chainfuncs(*funcs: Callable) -> Callable:
    funclist = funcs

    def execchain(*args: Any) -> None:
        for f in funclist:
            f()

    return execchain


def as_none(item: Any) -> Any:
    if isinstance(item, str) and len(item) == 0 or isinstance(item, int) and item == 0:
        return None
    return item
