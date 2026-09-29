"""``execsql shell``: an interactive session for SQL and metacommands.

The session is a script typed one input at a time: each input runs as the
next lines of that script, through the engine the debug REPL shares
(:mod:`execsql.interactive`). ``~local`` variables and SCRIPT blocks last for
the whole session.

When stdin is not a terminal, lines are read without prompts, so a session can
be piped in: ``execsql shell data.db < session.sql``.
"""

from __future__ import annotations

import sys
from typing import Any

import execsql.state as _state
from execsql.debug.repl import _BOLD, _CYAN, _DIM, _YELLOW, _c, _reset_color_cache, _write
from execsql.interactive import Prompt, common_dot_command, read_eval_loop, uncommitted, unknown_dot_command

__all__ = ["run_shell"]

_HELP = """\
  SQL                       End a statement with ;  (it may span lines)
  -- !x! METACOMMAND        Run a metacommand; !x! METACOMMAND works too
  IF / LOOP / BEGIN BATCH   Blocks stay open until their ENDIF / END LOOP / END BATCH
  .vars [VAR | all]         List substitution variables, or print one; all adds &env
  .set VAR VALUE            Set a substitution variable
  .scripts [NAME]           List SCRIPT blocks, or show one
  .cancel                   Discard a statement or block you are typing
  .help                     Show this help
  .quit                     Leave the shell (also .exit, .q, Ctrl-D)

  The prompt shows execsql*> while SQL is not committed as it runs
  (AUTOCOMMIT OFF). End that work with COMMIT; or ROLLBACK;.
"""


class _ShellPrompt(Prompt):
    name = "execsql"
    source = "<shell>"

    def dot_command(self, command: str, argument: str, line: str) -> bool:
        if command in ("quit", "exit", "q"):
            return False
        if command in ("help", "h"):
            _write(_HELP)
        elif not common_dot_command(command, argument, line):
            unknown_dot_command(line)
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
    from execsql.script.executor import open_session

    _reset_color_cache()
    open_session(_ShellPrompt.source)
    interactive = sys.stdin.isatty()
    if interactive:
        try:
            import readline as _readline  # noqa: F401 — enables history and line editing
        except ImportError:
            pass  # not available on Windows
        _write(_banner(_state.dbs.current() if _state.dbs is not None else None))
    read_eval_loop(_ShellPrompt(), interactive=interactive)
    if uncommitted():
        _write(
            f"  {_c(_YELLOW, 'Not committed:')} AUTOCOMMIT is OFF, so work since the last COMMIT is rolled back.\n",
        )
