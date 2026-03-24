from __future__ import annotations
from execsql.exceptions import ErrInfo

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
    except Exception:
        raise ErrInfo("db", sql, exception_msg=exception_desc())
    nrows = rec[0][0]
    return nrows > 0


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
    except Exception:
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"The value {{{val}}} is not numeric.",
        )
    return v == 0


def xf_isgt(**kwargs: Any) -> bool:
    val1 = kwargs["value1"].strip()
    val2 = kwargs["value2"].strip()
    try:
        v1 = float(val1)
        v2 = float(val2)
    except Exception:
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Values {{{val1}}} and {{{val2}}} are not both numeric.",
        )
    return v1 > v2


def xf_isgte(**kwargs: Any) -> bool:
    val1 = kwargs["value1"].strip()
    val2 = kwargs["value2"].strip()
    try:
        v1 = float(val1)
        v2 = float(val2)
    except Exception:
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Values {{{val1}}} and {{{val2}}} are not both numeric.",
        )
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
    mcl.add(r"^\s*HASROWS\((?P<queryname>[^)]+)\)", xf_hasrows)
    mcl.add(r"^\s*HAS_ROWS\((?P<queryname>[^)]+)\)", xf_hasrows)

    # Status predicates
    mcl.add(r"^\s*sql_error\(\s*\)", xf_sqlerror)
    mcl.add(r"^\s*dialog_canceled\(\s*\)", xf_dialogcanceled)
    mcl.add(r"^\s*metacommand_error\(\s*\)", xf_metacommanderror)
    mcl.add(r"^\s*CONSOLE_ON", xf_console)

    # FILE / DIRECTORY
    mcl.add(ins_fn_rxs(r"^FILE_EXISTS\(\s*", r"\)"), xf_fileexists)
    mcl.add(r'^DIRECTORY_EXISTS\(\s*("?)(?P<dirname>[^")]+)\1\)', xf_direxists)

    # Database object existence
    mcl.add(
        (
            r"^SCHEMA_EXISTS\(\s*(?P<schema>[A-Za-z0-9_\-\: ]+)\s*\)",
            r'^SCHEMA_EXISTS\(\s*"(?P<schema>[A-Za-z0-9_\-\: ]+)"\s*\)',
        ),
        xf_schemaexists,
    )
    mcl.add(
        (
            r"^TABLE_EXISTS\(\s*(?:(?P<schema>[A-Za-z0-9_\-\/\: ]+)\.)?(?P<tablename>[A-Za-z0-9_\-\/\: ]+)\)",
            r"^TABLE_EXISTS\(\s*(?:\[(?P<schema>[A-Za-z0-9_\-\/\: ]+)\]\.)?\[(?P<tablename>[A-Za-z0-9_\-\/\: ]+)\]\)",
            r'^TABLE_EXISTS\(\s*(?:"(?P<schema>[A-Za-z0-9_\-\/\: ]+)"\.)?"(?P<tablename>[A-Za-z0-9_\-\/\: ]+)"\)',
            r"^TABLE_EXISTS\(\s*(?:(?P<schema>[A-Za-z0-9_\-\/]+)\.)?(?P<tablename>[A-Za-z0-9_\-\/]+)\)",
        ),
        xf_tableexists,
    )
    mcl.add(
        (
            r"^ROLE_EXISTS\(\s*(?P<role>[A-Za-z0-9_\-\:\$ ]+)\s*\)",
            r'^ROLE_EXISTS\(\s*"(?P<role>[A-Za-z0-9_\-\:\$ ]+)"\s*\)',
        ),
        xf_roleexists,
    )
    mcl.add(r'^\s*VIEW_EXISTS\(\s*("?)(?P<viewname>[^")]+)\1\)', xf_viewexists)
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
    )
    mcl.add(r"^\s*ALIAS_DEFINED\s*\(\s*(?P<alias>\w+)\s*\)", xf_aliasdefined)

    # Substitution variable predicates
    mcl.add(r"^SUB_DEFINED\s*\(\s*(?P<match_str>[\$&@~#]?\w+)\s*\)", xf_sub_defined)
    mcl.add(r"^SUB_EMPTY\s*\(\s*(?P<match_str>[\$&@~#]?\w+)\s*\)", xf_sub_empty)
    mcl.add(r"^\s*SCRIPT_EXISTS\s*\(\s*(?P<script_id>\w+)\s*\)", xf_script_exists)

    # Comparison predicates
    mcl.add(r"^\s*EQUAL(S)?\s*\(\s*(?P<string1>[^ )]+)\s*,\s*(?P<string2>[^ )]+)\s*\)", xf_equals)
    mcl.add(r'^\s*EQUAL(S)?\s*\(\s*"(?P<string1>[^"]+)"\s*,\s*(?P<string2>[^ )]+)\s*\)', xf_equals)
    mcl.add(r'^\s*EQUAL(S)?\s*\(\s*(?P<string1>[^ )]+)\s*,\s*"(?P<string2>[^"]+)"\s*\)', xf_equals)
    mcl.add(r'^\s*EQUAL(S)?\s*\(\s*"(?P<string1>[^"]+)"\s*,\s*"(?P<string2>[^"]+)"\s*\)', xf_equals)
    mcl.add(r"^\s*IDENTICAL\s*\(\s*(?P<string1>[^ ,)]+)\s*,\s*(?P<string2>[^ )]+)\s*\)", xf_identical)
    mcl.add(r'^\s*IDENTICAL\s*\(\s*"(?P<string1>[^"]+)"\s*,\s*(?P<string2>[^ )]+)\s*\)', xf_identical)
    mcl.add(r'^\s*IDENTICAL\s*\(\s*(?P<string1>[^ ,]+)\s*,\s*"(?P<string2>[^"]+)"\s*\)', xf_identical)
    mcl.add(r'^\s*IDENTICAL\s*\(\s*"(?P<string1>[^"]+)"\s*,\s*"(?P<string2>[^"]+)"\s*\)', xf_identical)
    mcl.add(r'^\s*IS_NULL\(\s*(?P<item>"[^"]*")\s*\)', xf_isnull)
    mcl.add(r"^\s*IS_ZERO\(\s*(?P<value>[^)]*)\s*\)", xf_iszero)
    mcl.add(r"^\s*IS_GT\(\s*(?P<value1>[^)]*)\s*,\s*(?P<value2>[^)]*)\s*\)", xf_isgt)
    mcl.add(r"^\s*IS_GTE\(\s*(?P<value1>[^)]*)\s*,\s*(?P<value2>[^)]*)\s*\)", xf_isgte)
    mcl.add(r"^\s*IS_TRUE\(\s*(?P<value>[^)]*)\s*\)", xf_istrue)

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
    )

    # Database type / name
    mcl.add(
        (
            r"^\s*DBMS\(\s*(?P<dbms>[A-Z0-9_\-\(\/\\\. ]+)\s*\)",
            r'^\s*DBMS\(\s*"(?P<dbms>[A-Z0-9_\-\(\)\/\\\. ]+)"\s*\)',
        ),
        xf_dbms,
    )
    mcl.add(
        (
            r"^\s*DATABASE_NAME\(\s*(?P<dbname>[A-Z0-9_;\-\(\/\\\. ]+)\s*\)",
            r'^\s*DATABASE_NAME\(\s*"(?P<dbname>[A-Z0-9_;\-\(\)\/\\\. ]+)"\s*\)',
        ),
        xf_dbname,
    )

    # File modification time comparisons
    mcl.add(
        ins_fn_rxs(
            r"^\s*NEWER_FILE\s*\(\s*",
            ins_fn_rxs(r"\s*,\s*", r"\s*\)", symbolicname="file2"),
            symbolicname="file1",
        ),
        xf_newer_file,
    )
    mcl.add(
        ins_fn_rxs(
            r"^\s*NEWER_DATE\s*\(\s*",
            r"\s*,\s*(?P<datestr>[^)]+)\s*\)",
            symbolicname="file1",
        ),
        xf_newer_date,
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
