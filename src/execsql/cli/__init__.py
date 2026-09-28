"""Command-line interface for execsql.

Parses arguments via Typer, then delegates to :func:`_run` for state
initialisation, database connection, and script execution.

Submodules:

- :mod:`execsql.cli.application` — the Typer app, its command group, and plain help rendering
- :mod:`execsql.cli.commands`  — one module per command (``run``, ``format``, ``lint``)
- :mod:`execsql.cli.dispatch`  — the rule that inserts ``run`` when no command is given
- :mod:`execsql.cli.help`      — metacommand/encoding tables, --init-config, console objects
- :mod:`execsql.cli.dsn`       — Connection-string (DSN URL) parser
- :mod:`execsql.cli.run`       — Core execution logic (``_run``, ``_connect_initial_db``, ``_ping_db``, ``_print_dry_run``, ``_print_profile``)
- :mod:`execsql.cli.lint`      — AST-based static analyser behind ``execsql lint``, and its output formats
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

from execsql.cli import commands  # noqa: F401 — registers every command on app
from execsql.cli.application import app
from execsql.cli.commands.run import main
from execsql.cli.dsn import _parse_connection_string, _SCHEME_TO_DBTYPE  # noqa: F401 — re-export
from execsql.cli.help import _console, _err_console, _init_config, _print_encodings, _print_metacommands  # noqa: F401 — re-export
from execsql.cli.run import _connect_initial_db, _run  # noqa: F401 — re-export
from execsql.exceptions import ConfigError, ErrInfo

__all__ = [
    "_SCHEME_TO_DBTYPE",
    "_connect_initial_db",
    "_console",
    "_err_console",
    "_init_config",
    "_legacy_main",
    "_parse_connection_string",
    "_print_encodings",
    "_print_metacommands",
    "_run",
    "app",
    "main",
]


# ---------------------------------------------------------------------------
# Legacy entry point (kept for backwards compat with pyproject.toml script)
# ---------------------------------------------------------------------------


def _legacy_main() -> None:
    """Entry point that wraps the Typer app for use as a console_scripts target."""
    try:
        app()
    except SystemExit as exc:
        raise exc from exc
    except ErrInfo as exc:
        from execsql.utils.errors import exit_now

        exit_now(1, exc)
    except ConfigError as exc:
        strace = traceback.extract_tb(sys.exc_info()[2])[-1:]
        lno = strace[0][1]
        sys.exit(f"Configuration error on line {lno} of execsql: {exc}")
    except Exception:
        strace = traceback.extract_tb(sys.exc_info()[2])[-1:]
        lno = strace[0][1]
        msg = f"{Path(sys.argv[0]).name}: Uncaught exception {sys.exc_info()[0]} ({sys.exc_info()[1]}) on line {lno}"
        from execsql.utils.errors import exit_now

        exit_now(1, ErrInfo("exception", exception_msg=msg))


if __name__ == "__main__":
    _legacy_main()
