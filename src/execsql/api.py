"""Public Python API for execsql.

Provides :func:`run` — the single entry point for executing SQL scripts
programmatically from Python code (notebooks, pipelines, applications).

Usage::

    from execsql import run

    # Execute a script file against SQLite
    result = run(script="pipeline.sql", dsn="sqlite:///my.db")
    print(result.success, result.commands_run)

    # Execute inline SQL
    result = run(sql="CREATE TABLE t (id INT); INSERT INTO t VALUES (1);",
                 dsn="sqlite:///my.db")

    # With substitution variables
    result = run(script="etl.sql",
                 dsn="postgresql://user:pass@host/db",
                 variables={"SCHEMA": "public", "DATE": "2026-01-01"})

    # Error handling
    result = run(sql="SELECT * FROM nonexistent;", dsn="sqlite:///my.db")
    if not result.success:
        for err in result.errors:
            print(f"{err.source}:{err.line}: {err.message}")
"""

from __future__ import annotations

import dataclasses
import datetime
import io
import os
import time
from pathlib import Path
from typing import Any

from execsql.cli.dsn import _parse_connection_string
from execsql.config import ConfigData, StatObj, WriteHooks
from execsql.exceptions import ErrInfo
from execsql.state import RuntimeContext, active_context

__all__ = ["run", "ScriptResult", "ScriptError"]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ScriptError:
    """A single error encountered during script execution.

    Attributes:
        message: Human-readable error description.
        source: Script file path or ``"<inline>"``.
        line: Source line number, or ``None`` if unknown.
        sql: The SQL statement that caused the error, if applicable.
    """

    message: str
    source: str = "<unknown>"
    line: int | None = None
    sql: str | None = None


@dataclasses.dataclass(frozen=True)
class ScriptResult:
    """Result of a script execution via :func:`run`.

    Attributes:
        success: ``True`` if execution completed without errors.
        commands_run: Number of SQL statements and metacommands executed.
        elapsed: Wall-clock execution time in seconds.
        errors: List of errors encountered (empty on success).
        variables: Final state of all user-defined substitution variables
            (``$``-prefixed names, without the ``$``).
    """

    success: bool
    commands_run: int
    elapsed: float
    errors: list[ScriptError]
    variables: dict[str, str]

    def raise_on_error(self) -> None:
        """Raise :class:`ExecSqlError` if the script failed.

        Convenience for callers who prefer exceptions over checking
        :attr:`success`.
        """
        if not self.success:
            msgs = "; ".join(e.message for e in self.errors[:3])
            if len(self.errors) > 3:
                msgs += f" (and {len(self.errors) - 3} more)"
            raise ExecSqlError(msgs, result=self)


class ExecSqlError(Exception):
    """Raised by :meth:`ScriptResult.raise_on_error` when a script fails."""

    def __init__(self, message: str, result: ScriptResult) -> None:
        super().__init__(message)
        self.result = result


# ---------------------------------------------------------------------------
# Minimal config for library use (skips config file search)
# ---------------------------------------------------------------------------


class _LibraryConfig:
    """Lightweight configuration for :func:`run` that skips INI file search.

    Provides the same attribute interface as :class:`ConfigData` but only
    sets the defaults needed for script execution.  No filesystem I/O at
    construction time.
    """

    def __init__(self, **overrides: Any) -> None:
        # Connection (overridden by run())
        self.db_type = "l"
        self.server: str | None = None
        self.port: int | None = None
        self.db: str | None = None
        self.db_file: str | None = None
        self.username: str | None = None
        self.passwd_prompt = False
        self.use_keyring = False
        self.new_db = False
        self.access_username: str | None = None

        # Encoding
        self.script_encoding = "utf-8"
        self.output_encoding = "utf-8"
        self.import_encoding = "utf-8"
        self.db_encoding: str | None = None
        self.enc_err_disposition: str | None = None

        # Runtime
        self.user_logfile = False
        self.gui_level = 0
        self.gui_framework = "tkinter"
        self.gui_wait_on_exit = False
        self.gui_wait_on_error_halt = False
        self.write_warnings = False
        self.make_export_dirs = False
        self.tee_write_log = False
        self.log_sql = False
        self.log_datavars = False
        self.show_progress = False
        self.max_log_size_mb = 0

        # Data handling
        self.boolean_int = True
        self.boolean_words = False
        self.empty_strings = True
        self.only_strings = False
        self.empty_rows = True
        self.del_empty_cols = False
        self.create_col_hdrs = False
        self.trim_col_hdrs = "none"
        self.clean_col_hdrs = False
        self.fold_col_hdrs = "no"
        self.dedup_col_hdrs = False
        self.trim_strings = False
        self.replace_newlines = False
        self.scan_lines = 100
        self.import_buffer = 32 * 1024
        self.import_common_cols_only = False
        self.import_row_buffer = 1000
        self.import_progress_interval = 0
        self.export_row_buffer = 1000
        self.max_int = 2147483647
        self.quote_all_text = False
        self.hdf5_text_len = 1000
        self.outfile_open_timeout = 600
        self.zip_buffer_mb = 10
        self.dao_flush_delay_secs = 5.0
        self.access_use_numeric = False

        # Output
        self.write_prefix: str | None = None
        self.write_suffix: str | None = None
        self.css_file: str | None = None
        self.css_styles: str | None = None
        self.template_processor: str | None = None
        self.gui_console_height = 25
        self.gui_console_width = 100

        # Email (needed by ON ERROR_HALT EMAIL handlers)
        self.smtp_host: str | None = None
        self.smtp_port: int | None = None
        self.smtp_username: str | None = None
        self.smtp_password: str | None = None
        self.smtp_ssl = False
        self.smtp_tls = False
        self.email_format = "plain"
        self.email_css: str | None = None

        # Includes
        self.include_req: list = []
        self.include_opt: list = []

        # Config file tracking (for compatibility)
        self.files_read: list = []

        # Apply overrides
        for k, v in overrides.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# Database connection from DSN
# ---------------------------------------------------------------------------


def _connect_from_dsn(dsn: str, new_db: bool = False) -> Any:
    """Create a database connection from a DSN URL string.

    Returns a :class:`~execsql.db.base.Database` subclass instance.
    """
    from execsql.db.factory import (
        db_Access,
        db_Dsn,
        db_DuckDB,
        db_Firebird,
        db_MySQL,
        db_Oracle,
        db_Postgres,
        db_SQLite,
        db_SqlServer,
    )

    params = _parse_connection_string(dsn)
    db_type = params["db_type"]
    server = params["server"]
    db_name = params["db"]
    db_file = params["db_file"]
    user = params["user"]
    password = params["password"]
    port = params["port"]

    if db_type == "l":
        file = db_file or ":memory:"
        # In-memory databases are always "new"
        return db_SQLite(file, new_db=new_db or file == ":memory:")
    elif db_type == "k":
        file = db_file or ":memory:"
        return db_DuckDB(file, new_db=new_db or file == ":memory:")
    elif db_type == "p":
        return db_Postgres(
            server or "localhost",
            db_name,
            user=user,
            password=password,
            port=port or 5432,
            new_db=new_db,
        )
    elif db_type == "m":
        return db_MySQL(
            server or "localhost",
            db_name,
            user=user,
            password=password,
            port=port or 3306,
        )
    elif db_type == "s":
        return db_SqlServer(
            server or "localhost",
            db_name,
            user=user,
            password=password,
            port=port,
        )
    elif db_type == "o":
        return db_Oracle(
            server or "localhost",
            db_name,
            user=user,
            password=password,
            port=port or 1521,
        )
    elif db_type == "f":
        return db_Firebird(
            server or "localhost",
            db_name or db_file,
            user=user,
            password=password,
            port=port or 3050,
        )
    elif db_type == "a":
        return db_Access(db_file)
    elif db_type == "d":
        return db_Dsn(db_name, user=user, password=password)
    else:
        raise ValueError(f"Unsupported database type: {db_type!r}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run(
    script: str | Path | None = None,
    *,
    sql: str | None = None,
    dsn: str | None = None,
    connection: Any = None,
    variables: dict[str, str] | None = None,
    config_file: str | Path | None = None,
    encoding: str = "utf-8",
    halt_on_error: bool = True,
    new_db: bool = False,
    allow_system_cmd: bool = True,
) -> ScriptResult:
    """Execute a SQL script and return the result.

    Exactly one of *script* or *sql* must be provided.  Exactly one of
    *dsn* or *connection* must be provided.

    Args:
        script: Path to a ``.sql`` script file.
        sql: Inline SQL/metacommand string to execute.
        dsn: Database connection URL (e.g. ``"sqlite:///my.db"``,
            ``"postgresql://user:pass@host/db"``).
        connection: A pre-existing :class:`~execsql.db.base.Database`
            instance.  ``run()`` will NOT close this connection on exit.
        variables: Substitution variables as ``{"NAME": "value"}``.
            Keys without a ``$`` prefix get one added automatically.
        config_file: Optional execsql configuration file to load.
        encoding: Script file encoding (default ``"utf-8"``).
        halt_on_error: If ``True`` (default), stop on the first SQL
            error.  If ``False``, capture errors and continue.
        new_db: If ``True``, create the database if it does not exist
            (SQLite, PostgreSQL, DuckDB).
        allow_system_cmd: If ``False``, the SYSTEM_CMD (SHELL) metacommand
            is disabled and will raise an error if encountered.

    Returns:
        A :class:`ScriptResult` with execution outcome, timing, errors,
        and final variable state.

    Raises:
        ValueError: If the argument combination is invalid (e.g. both
            *script* and *sql* provided, or neither *dsn* nor *connection*).
        ExecSqlError: Only if the caller explicitly calls
            :meth:`ScriptResult.raise_on_error`.
    """
    # ------------------------------------------------------------------
    # Validate arguments
    # ------------------------------------------------------------------
    if script is not None and sql is not None:
        raise ValueError("Provide either 'script' or 'sql', not both.")
    if script is None and sql is None:
        raise ValueError("Either 'script' or 'sql' must be provided.")
    if dsn is not None and connection is not None:
        raise ValueError("Provide either 'dsn' or 'connection', not both.")
    if dsn is None and connection is None:
        raise ValueError("Either 'dsn' or 'connection' must be provided.")

    # ------------------------------------------------------------------
    # Parse the script into an AST
    # ------------------------------------------------------------------
    from execsql.script.parser import parse_script, parse_string

    try:
        if script is not None:
            tree = parse_script(str(script), encoding=encoding)
        else:
            tree = parse_string(sql, source_name="<inline>")
    except ErrInfo as exc:
        return ScriptResult(
            success=False,
            commands_run=0,
            elapsed=0.0,
            errors=[ScriptError(message=exc.errmsg(), source=str(script) if script else "<inline>")],
            variables={},
        )

    # ------------------------------------------------------------------
    # Build an isolated RuntimeContext
    # ------------------------------------------------------------------
    ctx = RuntimeContext()

    # Configuration
    conf_overrides: dict[str, Any] = {"script_encoding": encoding}
    if config_file is not None:
        # Load a real ConfigData with the explicit config file
        from execsql.script.variables import SubVarSet

        temp_subvars = SubVarSet()
        script_dir = str(Path(script).resolve().parent) if script else os.getcwd()
        conf = ConfigData(script_dir, temp_subvars, config_file=str(config_file))
        # Apply any overrides
        for k, v in conf_overrides.items():
            setattr(conf, k, v)
    else:
        conf = _LibraryConfig(**conf_overrides)

    # Substitution variables
    from execsql.script.variables import SubVarSet

    subvars = SubVarSet()

    # Seed essential built-in variables
    dt_now = datetime.datetime.now()
    subvars.add_substitution("$SCRIPT_START_TIME", dt_now.strftime("%Y-%m-%d %H:%M"))
    subvars.add_substitution("$DATE_TAG", dt_now.strftime("%Y%m%d"))
    subvars.add_substitution("$DATETIME_TAG", dt_now.strftime("%Y%m%d_%H%M"))
    subvars.add_substitution("$LAST_SQL", "")
    subvars.add_substitution("$LAST_ERROR", "")
    subvars.add_substitution("$ERROR_MESSAGE", "")
    subvars.add_substitution("$LAST_ROWCOUNT", None)
    subvars.add_substitution("$PATHSEP", os.sep)
    subvars.add_substitution("$STARTING_PATH", os.getcwd() + os.sep)
    import platform

    subvars.add_substitution("$HOSTNAME", platform.node())

    # User-supplied variables
    if variables:
        for name, value in variables.items():
            key = name if name.startswith("$") else f"${name}"
            subvars.add_substitution(key, str(value))

    # ------------------------------------------------------------------
    # Initialize state
    # ------------------------------------------------------------------
    from execsql.metacommands import DISPATCH_TABLE
    from execsql.metacommands.conditions import CONDITIONAL_TABLE

    ctx.subvars = subvars
    ctx.status = StatObj()
    ctx.status.halt_on_err = halt_on_error
    conf.allow_system_cmd = allow_system_cmd
    ctx.conf = conf

    # Capture output to a buffer (suppress stdout/stderr)
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    ctx.output = WriteHooks(stdout_buf.write, stderr_buf.write)

    # No log file for library use
    ctx.exec_log = _NoOpLogger()

    with active_context(ctx):
        # Initialize singletons (IfLevels, CounterVars, Timer, DatabasePool, etc.)
        from execsql.state import initialize

        initialize(conf, DISPATCH_TABLE, CONDITIONAL_TABLE)

        # ------------------------------------------------------------------
        # Connect to database
        # ------------------------------------------------------------------
        owns_connection = connection is None
        if dsn is not None:
            db = _connect_from_dsn(dsn, new_db=new_db)
        else:
            db = connection

        ctx.dbs.add("initial", db)
        ctx.subvars.add_substitution("$CURRENT_DBMS", db.type.dbms_id)
        ctx.subvars.add_substitution("$CURRENT_DATABASE", db.name())
        ctx.subvars.add_substitution("$SYSTEM_CMD_EXIT_STATUS", "0")

        # ------------------------------------------------------------------
        # Execute
        # ------------------------------------------------------------------
        from execsql.script.executor import execute

        errors: list[ScriptError] = []
        t0 = time.perf_counter()

        try:
            execute(tree, ctx=ctx)
        except SystemExit:
            # exit_now() calls sys.exit() — catch and convert to error
            _capture_errors(ctx, errors)
        except ErrInfo as exc:
            errors.append(
                ScriptError(
                    message=exc.errmsg(),
                    source=_last_source(ctx),
                    line=_last_line(ctx),
                    sql=getattr(exc, "command_text", None),
                ),
            )
        except Exception as exc:
            errors.append(ScriptError(message=str(exc), source="<runtime>"))

        elapsed = time.perf_counter() - t0

        # ------------------------------------------------------------------
        # Collect results
        # ------------------------------------------------------------------
        final_vars = {}
        if ctx.subvars is not None:
            for name, value in ctx.subvars.substitutions:
                # Include user vars and $-prefixed system vars
                # Skip environment (&), column (@), local (~), parameter (#) vars
                if not name or name[0] in ("&", "@", "~", "#"):
                    continue
                key = name.lstrip("$")
                final_vars[key] = str(value) if value is not None else ""

        # Close connection if we own it
        if owns_connection:
            try:
                ctx.dbs.closeall()
            except Exception:
                pass

    return ScriptResult(
        success=len(errors) == 0,
        commands_run=ctx.cmds_run,
        elapsed=elapsed,
        errors=errors,
        variables=final_vars,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capture_errors(ctx: RuntimeContext, errors: list[ScriptError]) -> None:
    """Extract error info from the current context after a SystemExit."""
    last_error = None
    error_msg = None
    if ctx.subvars is not None:
        subs = dict(ctx.subvars.substitutions)
        last_error = subs.get("$LAST_ERROR")
        error_msg = subs.get("$ERROR_MESSAGE")

    msg = error_msg or last_error or "Script execution failed"
    errors.append(
        ScriptError(
            message=str(msg),
            source=_last_source(ctx),
            line=_last_line(ctx),
            sql=str(last_error) if last_error else None,
        ),
    )


def _last_source(ctx: RuntimeContext) -> str:
    """Get the source file from the last executed command."""
    lc = ctx.last_command
    if lc is not None and hasattr(lc, "source"):
        return lc.source
    return "<unknown>"


def _last_line(ctx: RuntimeContext) -> int | None:
    """Get the line number from the last executed command."""
    lc = ctx.last_command
    if lc is not None and hasattr(lc, "line_no"):
        return lc.line_no
    return None


class _NoOpLogger:
    """Minimal logger that silently discards all messages.

    Satisfies the full ``exec_log`` (Logger) interface without writing
    to disk.  All methods are no-ops.
    """

    run_id: str = "library"

    def __getattr__(self, name: str) -> Any:
        """Return a no-op callable for any unimplemented log method."""
        if name.startswith("log_"):
            return lambda *args, **kwargs: None
        raise AttributeError(f"_NoOpLogger has no attribute {name!r}")

    def close(self) -> None:
        pass
