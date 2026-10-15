from __future__ import annotations

"""
SQL INSERT VALUES export for execsql.

Provides :func:`write_query_to_values`, which serializes a query result
set as a series of SQL ``INSERT INTO … VALUES (…)`` statements, suitable
for loading data into a database from a plain SQL file.
"""

import decimal
import re
from typing import Any

import execsql.state as _state
from execsql.exporters.zip import ZipWriter
from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc
from execsql.utils.fileio import filewriter_close

__all__ = ["export_values", "write_query_to_values"]


# How each DBMS joins strings and writes a character by its code.  A text
# value that execsql would misread when a script runs the file with INCLUDE (see
# _text_literal) is written as pieces joined this way.  (template, joiner, char)
_CONCAT: dict[str, tuple[str, str, str]] = {
    "MySQL": ("CONCAT({})", ", ", "CHAR({} USING utf8mb4)"),
    "SQL Server": ("({})", " + ", "CHAR({})"),
    "Access": ("({})", " & ", "Chr({})"),
    "SQLite": ("({})", " || ", "char({})"),
    "Firebird": ("({})", " || ", "ASCII_CHAR({})"),
}
# PostgreSQL, DuckDB, Oracle, and an ODBC DSN.
_CONCAT_DEFAULT = ("({})", " || ", "CHR({})")

# What execsql acts on when it runs the file: a line break (a line of the
# value could end the statement with ';' or start a '-- !x!' metacommand)
# and the start of a substitution variable (!!x!!, !'!x!'!, !"!x!"!, !{x}!).
_RX_UNSAFE = re.compile(r"\r\n|\r|\n|!(?=!|'!|\"!|\{)")
_LINE_BREAK_CODES = {"\r\n": (13, 10), "\r": (13,), "\n": (10,)}

# Column names written quoted: PostgreSQL's reserved key words, which cover
# the names other DBMSs also reject bare, plus KEY and INDEX (MySQL).
_RESERVED = frozenset(
    [
        "ALL",
        "ANALYSE",
        "ANALYZE",
        "AND",
        "ANY",
        "ARRAY",
        "AS",
        "ASC",
        "ASYMMETRIC",
        "BOTH",
        "CASE",
        "CAST",
        "CHECK",
        "COLLATE",
        "COLUMN",
        "CONSTRAINT",
        "CREATE",
        "CURRENT_CATALOG",
        "CURRENT_DATE",
        "CURRENT_ROLE",
        "CURRENT_TIME",
        "CURRENT_TIMESTAMP",
        "CURRENT_USER",
        "DEFAULT",
        "DEFERRABLE",
        "DESC",
        "DISTINCT",
        "DO",
        "ELSE",
        "END",
        "EXCEPT",
        "FALSE",
        "FETCH",
        "FOR",
        "FOREIGN",
        "FROM",
        "GRANT",
        "GROUP",
        "HAVING",
        "IN",
        "INDEX",
        "INITIALLY",
        "INTERSECT",
        "INTO",
        "KEY",
        "LATERAL",
        "LEADING",
        "LIMIT",
        "LOCALTIME",
        "LOCALTIMESTAMP",
        "NOT",
        "NULL",
        "OFFSET",
        "ON",
        "ONLY",
        "OR",
        "ORDER",
        "PLACING",
        "PRIMARY",
        "REFERENCES",
        "RETURNING",
        "SELECT",
        "SESSION_USER",
        "SOME",
        "SYMMETRIC",
        "SYSTEM_USER",
        "TABLE",
        "THEN",
        "TO",
        "TRAILING",
        "TRUE",
        "UNION",
        "UNIQUE",
        "USER",
        "USING",
        "VARIADIC",
        "WHEN",
        "WHERE",
        "WINDOW",
        "WITH",
    ],
)


def _text_literal(text: str, dbms: str | None) -> str:
    """*text* as a SQL string that execsql reads back unchanged when a script runs the file with INCLUDE.

    execsql reads a script line by line, substituting variables and treating
    a ``-- !x!`` line as a metacommand and a line ending in ``;`` as the end of
    a statement, inside a string literal too.  So a value holding a line
    break or the start of a variable reference is written as pieces, each
    free of both, joined in *dbms*'s syntax: ``('a' || CHR(10) || 'b')``.
    """
    if not _RX_UNSAFE.search(text):
        return "'" + text.replace("'", "''") + "'"
    template, joiner, char = _CONCAT.get(dbms or "", _CONCAT_DEFAULT)
    pieces: list[str] = []
    start = 0
    for m in _RX_UNSAFE.finditer(text):
        if m.group() == "!":  # end a piece after the '!', so no piece holds the whole marker
            pieces.append("'" + text[start : m.end()].replace("'", "''") + "'")
        else:
            if m.start() > start:
                pieces.append("'" + text[start : m.start()].replace("'", "''") + "'")
            pieces.extend(char.format(code) for code in _LINE_BREAK_CODES[m.group()])
        start = m.end()
    if start < len(text):
        pieces.append("'" + text[start:].replace("'", "''") + "'")
    return template.format(joiner.join(pieces))


def _sql_literal(value: Any, dbms: str | None = None) -> str:
    """Render a value as a SQL literal for an INSERT ... VALUES list.

    Only numbers are emitted bare.  Everything else is quoted, with embedded
    single quotes doubled — the SQL standard escape — and text execsql would
    misread when running the file is split into pieces (:func:`_text_literal`).

    Quoting is the safe default rather than the exception.  Previously anything
    that was not a string went out through ``str()`` unquoted, so a date became
    ``2026-09-24``, which SQL reads as arithmetic: PostgreSQL inserted 1993 and
    reported no error at all.  A timestamp, carrying a space, was a syntax
    error instead.  Any type this function has not been taught about is safer
    quoted than bare.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        # Checked before int — bool is a subclass of it.
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float | decimal.Decimal):
        return str(value)
    return _text_literal(str(value), dbms)


def _column_name(name: str, dbtype: Any) -> str:
    """*name* as written in the column list: quoted if it is not a plain, unreserved identifier."""
    if re.fullmatch(r"[A-Za-z_]\w*", name) and name.upper() not in _RESERVED:
        return name
    opening, closing = getattr(dbtype, "quotechars", ('"', '"'))
    if opening == closing:
        name = name.replace(opening, opening * 2)
    return opening + name + closing


def export_values(
    outfile: str,
    hdrs: list[str],
    rows: Any,
    append: bool = False,
    desc: str | None = None,
    zipfile: str | None = None,
    dbtype: Any = None,
) -> None:
    """Write pre-fetched rows as SQL INSERT … VALUES statements to a file or ZIP archive.

    *dbtype* is the exporting database's :class:`~execsql.types.DbType`: its
    identifier quotes and its string syntax are used where a name or a
    value needs them.  With no rows, the file holds a comment instead of an
    INSERT, which would be invalid SQL.
    """
    conf = _state.conf
    dbms = getattr(dbtype, "dbms_id", None)
    if outfile.lower() == "stdout":
        f = _state.output
    else:
        if zipfile is None:
            filewriter_close(outfile)
            from execsql.utils.fileio import EncodedFile

            ef = EncodedFile(outfile, conf.output_encoding)
            if append:
                f = ef.open("at")
            else:
                f = ef.open("wt")
        else:
            f = ZipWriter(zipfile, outfile, append)
    try:
        if desc is not None:
            f.write(f"-- {desc}\n")
        firstrow = True
        for r in rows:
            if firstrow:
                firstrow = False
                columns = ", ".join(_column_name(h, dbtype) for h in hdrs)
                f.write(f"INSERT INTO !!target_table!!\n    ({columns})\nVALUES\n")
            else:
                f.write(",\n")
            quoted_row = [_sql_literal(v, dbms) for v in r]
            f.write(f"    ({', '.join(quoted_row)})")
        if firstrow:
            f.write("-- The query returned no rows: nothing to insert.\n")
        else:
            f.write("\n    ;\n")
    finally:
        if outfile.lower() != "stdout":
            f.close()


def write_query_to_values(
    select_stmt: str,
    db: Any,
    outfile: str,
    append: bool = False,
    desc: str | None = None,
    zipfile: str | None = None,
) -> None:
    """Execute a SELECT and write the result set as SQL INSERT … VALUES statements."""
    try:
        hdrs, rows = db.select_rowsource(select_stmt)
    except ErrInfo:
        raise
    except Exception as e:
        raise ErrInfo("db", select_stmt, exception_msg=exception_desc()) from e
    export_values(outfile, hdrs, rows, append, desc, zipfile=zipfile, dbtype=getattr(db, "type", None))
