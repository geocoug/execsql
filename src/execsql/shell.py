"""``execsql shell``: an interactive session for SQL and metacommands.

Each input is parsed as a small script and run by the normal executor, so SQL,
metacommands and blocks (``IF`` … ``ENDIF``, ``LOOP``, ``BEGIN BATCH``) behave
exactly as they do in a script file. A block keeps the prompt open until it is
closed. Plain SQL is run directly so its results can be shown: variables are
substituted first, as in a script, and each statement is committed unless a
``BEGIN BATCH`` is open.

Input starting with ``.`` is a shell command (``.help``, ``.vars``, ``.set``,
``.quit``). A metacommand is typed as in a script, ``-- !x! EXPORT …``, or
without the comment marker, ``!x! EXPORT …``.

When stdin is not a terminal, lines are read without prompts, so a session can
be piped in: ``execsql shell data.db < session.sql``.
"""

from __future__ import annotations

import sys
from typing import Any

import execsql.state as _state
from execsql.debug.repl import (
    _BOLD,
    _CYAN,
    _DIM,
    _RED,
    _c,
    _print_all_vars,
    _print_table,
    _print_var,
    _reset_color_cache,
    _set_var,
    _write,
)
from execsql.exceptions import ErrInfo

__all__ = ["run_shell"]

_HELP = """\
  SQL                       End a statement with ;  (it may span lines)
  -- !x! METACOMMAND        Run a metacommand; !x! METACOMMAND works too
  IF / LOOP / BEGIN BATCH   Blocks stay open until their ENDIF / END LOOP / END BATCH
  .vars [VAR]               List substitution variables, or print one
  .set VAR VALUE            Set a substitution variable
  .cancel                   Discard a statement or block you are typing
  .help                     Show this help
  .quit                     Leave the shell (also .exit, .q, Ctrl-D)
"""


def _is_metacommand(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("--") and stripped[2:].lstrip().lower().startswith("!x!")


def _complete(line: str) -> bool:
    """Whether the input so far may be a whole statement: it ends with ; or is a metacommand."""
    return line.rstrip().endswith(";") or _is_metacommand(line)


def _one_line(exc: BaseException) -> str:
    return " ".join(str(exc).split())


def _run_query(sql: str) -> None:
    """Run one SQL statement after substitution, show its result, and commit unless in a batch."""
    from execsql.script.engine import substitute_vars

    db = _state.dbs.current() if _state.dbs is not None else None
    if db is None:
        _write("  (no database connection is active)\n")
        return
    text = substitute_vars(sql)
    with db._cursor() as curs:
        try:
            curs.execute(text)
        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                pass
            _write(f"  {_c(_RED, 'SQL error:')} {_one_line(exc)}\n")
            return
        try:
            _state.subvars.add_substitution("$LAST_ROWCOUNT", curs.rowcount)
        except Exception:
            pass
        if curs.description is not None:
            colnames = [d[0] for d in curs.description]
            rows = curs.fetchall()
        else:
            colnames, rows = [], []
            count = curs.rowcount if curs.rowcount is not None else -1
            word = "row" if count == 1 else "rows"
            _write(f"  {_c(_DIM, f'({count} {word} affected)' if count >= 0 else '(statement executed)')}\n")
    if colnames:
        _print_table(colnames, rows)
    if not _state.status.batch.in_batch():
        db.commit()


def _run_input(text: str) -> None:
    """Parse and run one complete input."""
    from execsql.script.ast import SqlStatement
    from execsql.script.executor import execute
    from execsql.script.parser import parse_string

    tree = parse_string(text + "\n", "<shell>")
    statements = [node for node in tree.body if isinstance(node, SqlStatement)]
    if tree.body and len(statements) == len(tree.body):
        for statement in statements:
            _run_query(statement.text)
        return
    execute(tree, session=True)


def _dot_command(line: str) -> bool:
    """Handle a ``.`` command; return ``False`` when the shell should end."""
    parts = line[1:].strip().split(None, 2)
    name = parts[0].lower() if parts else ""
    if name in ("quit", "exit", "q"):
        return False
    if name in ("help", "h"):
        _write(_HELP)
    elif name in ("vars", "v"):
        if len(parts) > 1:
            _print_var(parts[1])
        else:
            _print_all_vars()
    elif name in ("set", "s"):
        if len(parts) < 3:
            _write("  Usage: .set VAR VALUE\n")
        else:
            _set_var(parts[1], parts[2])
    else:
        _write(f"  Unknown command {_c(_BOLD, line.split()[0])}; .help lists them.\n")
    return True


def _banner(db: Any) -> str:
    where = db.name() if db is not None else "no database"
    if getattr(db, "db_name", None) == ":memory:":
        where = "an in-memory SQLite database (nothing is saved)"
    dbms = db.type.dbms_id if db is not None and getattr(db, "type", None) else ""
    return (
        f"{_c(_BOLD + _CYAN, 'execsql shell')} {_c(_DIM, '—')} {dbms} {where}\n"
        f"  {_c(_DIM, 'SQL ends with ;. .help for commands, .quit to leave.')}\n"
    )


def run_shell() -> None:
    """Read and run inputs until ``.quit`` or end of input."""
    _reset_color_cache()
    interactive = sys.stdin.isatty()
    if interactive:
        try:
            import readline as _readline  # noqa: F401 — enables history and line editing
        except ImportError:
            pass  # not available on Windows
        _write(_banner(_state.dbs.current() if _state.dbs is not None else None))

    buffer: list[str] = []
    while True:
        prompt = ("     ...> " if buffer else "execsql> ") if interactive else ""
        try:
            if interactive:
                line = input(prompt)
            else:
                line = sys.stdin.readline()
                if line == "":
                    raise EOFError
        except EOFError:
            if interactive:
                _write("\n")
            break
        except KeyboardInterrupt:
            if buffer:
                buffer.clear()
                _write("\n  (input discarded)\n")
                continue
            _write("\n")
            return
        line = line.rstrip("\n")
        stripped = line.strip()
        if not buffer and not stripped:
            continue
        if stripped.startswith(".") and not buffer:
            if not _dot_command(stripped):
                return
            continue
        if stripped.lower() == ".cancel":
            buffer.clear()
            _write("  (input discarded)\n")
            continue
        if stripped.lower().startswith("!x!"):
            line = "-- " + stripped
        buffer.append(line)
        if not _complete(line):
            continue
        text = "\n".join(buffer)
        try:
            _run_input(text)
        except ErrInfo as exc:
            if "at end of file" in str(exc):
                continue  # a block is still open; keep reading
            _write(f"  {_c(_RED, 'Error:')} {_one_line(exc)}\n")
        except SystemExit:
            raise
        except Exception as exc:
            _write(f"  {_c(_RED, 'Error:')} {_one_line(exc)}\n")
        buffer.clear()
    if buffer:
        _write(f"  {_c(_RED, 'Error:')} input ended inside an unfinished statement or block; it was not run.\n")
