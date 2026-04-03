"""PG_UPSERT metacommand handler.

Integrates pg-upsert (https://pg-upsert.readthedocs.io/) as an optional
dependency, providing QA-checked, FK-dependency-ordered upserts from a
staging schema to a base schema on PostgreSQL.

Requires: ``pip install execsql2[upsert]``
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.types import dbt_postgres
from execsql.utils.errors import exception_desc


# ---------------------------------------------------------------------------
# Keyword parser for the trailing portion after TABLES
# ---------------------------------------------------------------------------

_KW_METHOD = re.compile(r"\bMETHOD\s+(upsert|update|insert)\b", re.IGNORECASE)
_KW_EXCLUDE = re.compile(
    r"\bEXCLUDE\s+([\w\s,]+?)(?=\s+(?:METHOD|COMMIT|INTERACTIVE|COMPACT|EXCLUDE_NULL|LOGFILE|CLEANUP)\b|\s*$)",
    re.IGNORECASE,
)
_KW_EXCLUDE_NULL = re.compile(
    r"\bEXCLUDE_NULL\s+([\w\s,]+?)(?=\s+(?:METHOD|COMMIT|INTERACTIVE|COMPACT|EXCLUDE|LOGFILE|CLEANUP)\b|\s*$)",
    re.IGNORECASE,
)
_KW_COMMIT = re.compile(r"\bCOMMIT\b", re.IGNORECASE)
_KW_INTERACTIVE = re.compile(r"\bINTERACTIVE\b", re.IGNORECASE)
_KW_COMPACT = re.compile(r"\bCOMPACT\b", re.IGNORECASE)
_KW_CLEANUP = re.compile(r"\bCLEANUP\b", re.IGNORECASE)
_KW_LOGFILE = re.compile(r"""\bLOGFILE\s+(?:"([^"]+)"|'([^']+)'|(\S+))""", re.IGNORECASE)

# All recognized keywords — used to split table names from options.
_ALL_KEYWORDS = re.compile(
    r"\b(?:METHOD|COMMIT|INTERACTIVE|COMPACT|EXCLUDE_NULL|EXCLUDE|LOGFILE|CLEANUP)\b",
    re.IGNORECASE,
)


def _parse_tables_and_options(tail: str) -> dict[str, Any]:
    """Parse the trailing text after ``TABLES`` into table names and options.

    Parameters
    ----------
    tail:
        Everything captured after the ``TABLES`` keyword in the regex.

    Returns
    -------
    dict with keys: tables, method, commit, interactive, compact,
    exclude_cols, exclude_null_check_cols.
    """
    # Split at the first keyword to isolate the table list.
    kw_match = _ALL_KEYWORDS.search(tail)
    if kw_match:
        table_part = tail[: kw_match.start()]
        opts_part = tail[kw_match.start() :]
    else:
        table_part = tail
        opts_part = ""

    tables = [t.strip() for t in table_part.split(",") if t.strip()]

    method = "upsert"
    m = _KW_METHOD.search(opts_part)
    if m:
        method = m.group(1).lower()

    exclude_cols: list[str] = []
    m = _KW_EXCLUDE.search(opts_part)
    if m:
        exclude_cols = [c.strip() for c in m.group(1).split(",") if c.strip()]

    exclude_null: list[str] = []
    m = _KW_EXCLUDE_NULL.search(opts_part)
    if m:
        exclude_null = [c.strip() for c in m.group(1).split(",") if c.strip()]

    logfile: str | None = None
    m = _KW_LOGFILE.search(opts_part)
    if m:
        logfile = m.group(1) or m.group(2) or m.group(3)

    return {
        "tables": tables,
        "method": method,
        "commit": bool(_KW_COMMIT.search(opts_part)),
        "interactive": bool(_KW_INTERACTIVE.search(opts_part)),
        "compact": bool(_KW_COMPACT.search(opts_part)),
        "exclude_cols": exclude_cols,
        "exclude_null_check_cols": exclude_null,
        "logfile": logfile,
        "cleanup": bool(_KW_CLEANUP.search(opts_part)),
    }


# ---------------------------------------------------------------------------
# Logging bridge: pg_upsert.display → execsql exec_log
# ---------------------------------------------------------------------------


class _ExecLogHandler(logging.Handler):
    """Route pg_upsert's plain-text file logger to execsql's exec_log."""

    def __init__(self, exec_log: Any) -> None:
        super().__init__()
        self._exec_log = exec_log

    def emit(self, record: logging.LogRecord) -> None:
        self._exec_log.log_user_msg(self.format(record))


class _FileWriterHandler(logging.Handler):
    """Route pg_upsert log messages through execsql's async FileWriter.

    This ensures that pg-upsert log output and execsql WRITE TEE output
    arrive in the same order they were issued, since both go through the
    same FileWriter queue.
    """

    def __init__(self, filename: str) -> None:
        super().__init__()
        self._filename = filename

    def emit(self, record: logging.LogRecord) -> None:
        from execsql.utils.fileio import filewriter_write

        filewriter_write(self._filename, self.format(record) + "\n")


# ---------------------------------------------------------------------------
# Result → substitution variables
# ---------------------------------------------------------------------------


def _set_subvars(result: Any) -> None:
    """Populate ``$PG_UPSERT_*`` substitution variables from an UpsertResult."""
    sv = _state.subvars.add_substitution
    sv("$PG_UPSERT_QA_PASSED", str(result.qa_passed).upper())
    sv("$PG_UPSERT_ROWS_UPDATED", str(result.total_updated))
    sv("$PG_UPSERT_ROWS_INSERTED", str(result.total_inserted))
    sv("$PG_UPSERT_COMMITTED", str(result.committed).upper())
    sv("$PG_UPSERT_STAGING_SCHEMA", result.staging_schema)
    sv("$PG_UPSERT_BASE_SCHEMA", result.base_schema)
    sv("$PG_UPSERT_TABLES", ", ".join(t.table_name for t in result.tables))
    sv("$PG_UPSERT_METHOD", result.upsert_method)
    sv("$PG_UPSERT_DURATION", str(result.duration_seconds))
    sv("$PG_UPSERT_STARTED_AT", result.started_at)
    sv("$PG_UPSERT_FINISHED_AT", result.finished_at)
    sv("$PG_UPSERT_RESULT_JSON", json.dumps(result.to_dict(), separators=(",", ":")))


def _qa_failure_msg(result: Any) -> str:
    """Build a concise QA failure message listing which tables failed."""
    failed = [t.table_name for t in result.tables if not t.qa_passed]
    if failed:
        return f"PG_UPSERT QA failed for: {', '.join(failed)}"
    return "PG_UPSERT QA checks failed."


# ---------------------------------------------------------------------------
# Import guard + helpers
# ---------------------------------------------------------------------------


def _require_pg_upsert() -> None:
    """Raise ErrInfo if pg_upsert is not installed."""
    try:
        import pg_upsert  # noqa: F401
    except ImportError as exc:
        raise ErrInfo(
            "exception",
            other_msg=("PG_UPSERT requires the pg-upsert package. Install it with: pip install execsql2[upsert]"),
        ) from exc


def _require_postgres(db: Any, metacommandline: str | None) -> None:
    """Raise ErrInfo if the current connection is not PostgreSQL."""
    if db.type != dbt_postgres:
        raise ErrInfo(
            "cmd",
            command_text=metacommandline,
            other_msg=(f"PG_UPSERT requires a PostgreSQL connection. Current DBMS: {db.type.dbms_id}"),
        )


def _build_result_from_qa_errors(ups: Any) -> Any:
    """Build an UpsertResult from ``ups.qa_errors`` after a QA/CHECK run."""
    from pg_upsert.models import TableResult, UpsertResult

    table_results: dict[str, Any] = {}
    for table_name in ups.tables:
        table_results[table_name] = TableResult(table_name=table_name)
    for err in ups.qa_errors:
        if err.table in table_results:
            table_results[err.table].qa_errors.append(err)
    return UpsertResult(
        tables=list(table_results.values()),
        committed=False,
        staging_schema=ups.staging_schema,
        base_schema=ups.base_schema,
        upsert_method=ups.upsert_method,
    )


def _make_callback() -> Any:
    """Return a pg-upsert pipeline callback that sets per-table subvars."""
    from pg_upsert import CallbackEvent

    def _on_event(event: Any) -> None:
        sv = _state.subvars.add_substitution
        sv("$PG_UPSERT_CURRENT_TABLE", event.table)
        if event.event == CallbackEvent.QA_TABLE_COMPLETE:
            sv("$PG_UPSERT_TABLE_QA_PASSED", str(event.qa_passed).upper())
        elif event.event == CallbackEvent.UPSERT_TABLE_COMPLETE:
            sv("$PG_UPSERT_TABLE_ROWS_UPDATED", str(event.rows_updated))
            sv("$PG_UPSERT_TABLE_ROWS_INSERTED", str(event.rows_inserted))

    return _on_event


def _create_pgupsert(
    db: Any,
    staging_schema: str,
    base_schema: str,
    opts: dict[str, Any],
) -> Any:
    """Create and return a PgUpsert instance with execsql's connection."""
    from pg_upsert import PgUpsert

    ui_mode = "tkinter"
    if _state.conf:
        ui_mode = _state.conf.gui_framework

    ups = PgUpsert(
        conn=db.conn,
        staging_schema=staging_schema,
        base_schema=base_schema,
        tables=opts["tables"],
        do_commit=opts["commit"],
        interactive=opts["interactive"],
        compact=opts["compact"],
        upsert_method=opts["method"],
        exclude_cols=opts["exclude_cols"],
        exclude_null_check_cols=opts["exclude_null_check_cols"],
        ui_mode=ui_mode,
        callback=_make_callback(),
    )
    return ups


def _attach_log_handlers(
    logfile: str | None = None,
) -> tuple[list[logging.Logger], list[logging.Handler], dict[str, int]]:
    """Attach logging handlers to pg_upsert loggers.

    Always attaches the exec_log bridge to ``pg_upsert.display``.
    If *logfile* is given, also attaches a FileHandler (append mode) to both
    ``pg_upsert`` and ``pg_upsert.display`` — matching pg-upsert CLI behavior.

    Returns (loggers, handlers) so the caller can detach in a finally block.
    """
    display_logger = logging.getLogger("pg_upsert.display")
    # pg-upsert's display logger has propagate=False and level=NOTSET, which
    # gives it an effective level of WARNING (inherited from root).  Its messages
    # are logged at INFO, so we must explicitly lower the level.
    prev_display_level = display_logger.level
    if display_logger.getEffectiveLevel() > logging.INFO:
        display_logger.setLevel(logging.INFO)

    exec_handler = _ExecLogHandler(_state.exec_log)
    display_logger.addHandler(exec_handler)

    loggers: list[logging.Logger] = [display_logger]
    handlers: list[logging.Handler] = [exec_handler]
    prev_levels: dict[str, int] = {"pg_upsert.display": prev_display_level}

    if logfile:
        file_handler = _FileWriterHandler(logfile)
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        # Attach to both loggers, same as pg-upsert CLI does
        main_logger = logging.getLogger("pg_upsert")
        prev_levels["pg_upsert"] = main_logger.level
        if main_logger.getEffectiveLevel() > logging.INFO:
            main_logger.setLevel(logging.INFO)
        main_logger.addHandler(file_handler)
        display_logger.addHandler(file_handler)
        loggers.append(main_logger)
        handlers.append(file_handler)

    return loggers, handlers, prev_levels


def _detach_log_handlers(
    loggers: list[logging.Logger],
    handlers: list[logging.Handler],
    prev_levels: dict[str, int],
) -> None:
    """Remove all handlers added by ``_attach_log_handlers``."""
    for handler in handlers:
        for lgr in loggers:
            lgr.removeHandler(handler)
        if hasattr(handler, "close"):
            handler.close()
    # Restore original logger levels
    for name, level in prev_levels.items():
        logging.getLogger(name).setLevel(level)


def _run_with_autocommit_guard(db: Any, fn: Any) -> Any:
    """Temporarily disable autocommit, run *fn*, then restore."""
    was_autocommit = db.autocommit
    if was_autocommit:
        db.autocommit_off()
    try:
        return fn()
    finally:
        if was_autocommit:
            db.autocommit_on()


def _handle_pg_upsert_errors(fn: Any, metacommandline: str | None) -> Any:
    """Run *fn*, translating pg-upsert exceptions to ErrInfo."""
    from pg_upsert import UserCancelledError

    try:
        return fn()
    except UserCancelledError as exc:
        raise ErrInfo(
            "cmd",
            command_text=metacommandline,
            other_msg="PG_UPSERT cancelled by user.",
        ) from exc
    except ErrInfo:
        raise
    except Exception as exc:
        raise ErrInfo(
            "exception",
            exception_msg=exception_desc(),
            other_msg="PG_UPSERT failed unexpectedly.",
        ) from exc


# ---------------------------------------------------------------------------
# Metacommand handlers
# ---------------------------------------------------------------------------


def x_pg_upsert(**kwargs: Any) -> None:
    """PG_UPSERT FROM <staging> TO <base> TABLES <t1>, <t2> [options]

    Full pipeline: QA checks → upsert → optional commit.
    """
    _require_pg_upsert()
    db = _state.dbs.current()
    metacommandline = kwargs.get("metacommandline")
    _require_postgres(db, metacommandline)

    staging = kwargs["staging_schema"]
    base = kwargs["base_schema"]
    opts = _parse_tables_and_options(kwargs["tail"])

    ups = _create_pgupsert(db, staging, base, opts)
    loggers, handlers, prev_levels = _attach_log_handlers(opts.get("logfile"))

    try:
        result = _run_with_autocommit_guard(
            db,
            lambda: _handle_pg_upsert_errors(ups.run, metacommandline),
        )
    finally:
        _detach_log_handlers(loggers, handlers, prev_levels)

    _set_subvars(result)
    if opts.get("cleanup"):
        ups.cleanup()

    if not result.qa_passed:
        raise ErrInfo(
            "cmd",
            command_text=metacommandline,
            other_msg=_qa_failure_msg(result),
        )


def x_pg_upsert_qa(**kwargs: Any) -> None:
    """PG_UPSERT QA FROM <staging> TO <base> TABLES <t1>, <t2> [options]

    QA-only mode: run all QA checks without upserting.
    """
    _require_pg_upsert()
    db = _state.dbs.current()
    metacommandline = kwargs.get("metacommandline")
    _require_postgres(db, metacommandline)

    staging = kwargs["staging_schema"]
    base = kwargs["base_schema"]
    opts = _parse_tables_and_options(kwargs["tail"])
    opts["commit"] = False  # QA-only never commits

    ups = _create_pgupsert(db, staging, base, opts)
    loggers, handlers, prev_levels = _attach_log_handlers(opts.get("logfile"))

    try:
        _run_with_autocommit_guard(
            db,
            lambda: _handle_pg_upsert_errors(ups.qa_all, metacommandline),
        )
    finally:
        _detach_log_handlers(loggers, handlers, prev_levels)

    result = _build_result_from_qa_errors(ups)
    _set_subvars(result)
    if opts.get("cleanup"):
        ups.cleanup()

    if not result.qa_passed:
        raise ErrInfo(
            "cmd",
            command_text=metacommandline,
            other_msg=_qa_failure_msg(result),
        )


def x_pg_upsert_check(**kwargs: Any) -> None:
    """PG_UPSERT CHECK FROM <staging> TO <base> TABLES <t1>, <t2>

    Schema check only: column existence + type mismatch.
    """
    _require_pg_upsert()
    db = _state.dbs.current()
    metacommandline = kwargs.get("metacommandline")
    _require_postgres(db, metacommandline)

    staging = kwargs["staging_schema"]
    base = kwargs["base_schema"]
    opts = _parse_tables_and_options(kwargs["tail"])
    opts["commit"] = False

    ups = _create_pgupsert(db, staging, base, opts)
    loggers, handlers, prev_levels = _attach_log_handlers(opts.get("logfile"))

    try:
        _run_with_autocommit_guard(
            db,
            lambda: _handle_pg_upsert_errors(
                lambda: ups.qa_column_existence().qa_type_mismatch(),
                metacommandline,
            ),
        )
    finally:
        _detach_log_handlers(loggers, handlers, prev_levels)

    result = _build_result_from_qa_errors(ups)
    _set_subvars(result)
    if opts.get("cleanup"):
        ups.cleanup()

    if not result.qa_passed:
        raise ErrInfo(
            "cmd",
            command_text=metacommandline,
            other_msg=_qa_failure_msg(result),
        )
