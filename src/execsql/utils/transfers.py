"""Transfer lifecycle logging without changing data, transactions, or query execution.

Only payload queries explicitly selected by exporters contribute read counts.
Streaming counts become known at EOF, never from a driver's rowcount estimate.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
import time
from typing import TYPE_CHECKING, Any, TypeVar, cast

if TYPE_CHECKING:
    from execsql.utils.fileio import Logger

import execsql.state as state


@dataclass
class _Transfer:
    operation: str
    logger: Logger
    fields: dict[str, str]
    count_name: str
    started: float
    rows: int | None = None
    finished: bool = False

    def finish(self, outcome: str) -> None:
        if self.finished:
            return
        self.finished = True
        self.logger.log_transfer(
            self.operation,
            outcome,
            self.fields,
            rows=self.rows if outcome == "completed" else None,
            count_name=self.count_name,
            duration=time.monotonic() - self.started,
        )


_active: ContextVar[_Transfer | None] = ContextVar("execsql_transfer", default=None)
_query: ContextVar[tuple[_Transfer, str] | None] = ContextVar("execsql_transfer_query", default=None)
_F = TypeVar("_F", bound=Callable[..., Any])


def finish_active_transfer(logger: Logger, outcome: str) -> None:
    """Finalize before exit_now closes the log (e.g. a missing optional exporter)."""
    transfer = _active.get()
    if transfer is not None and transfer.logger is logger:
        transfer.finish(outcome)


def loaded_rows(rows: int) -> None:
    """Use the loader's existing successful insert count, including multiple sheets."""
    transfer = _active.get()
    if transfer is not None:
        transfer.rows = (transfer.rows or 0) + rows


def load_operation() -> str:
    """Name the active loader, including COPY's use of populate_table."""
    transfer = _active.get()
    return transfer.operation if transfer is not None else "IMPORT"


@contextmanager
def payload_query(sql: str) -> Iterator[None]:
    """Select the export query whose consumed rows should be counted (excluding TEE)."""
    transfer = _active.get()
    token = _query.set((transfer, sql) if transfer is not None and transfer.operation == "EXPORT" else None)
    try:
        yield
    finally:
        _query.reset(token)


def query_counter(sql: str) -> Callable[[int], None] | None:
    """Capture a payload query's completion callback before its streaming scope ends."""
    query = _query.get()
    if query is None or query[1].removesuffix(";") != sql.removesuffix(";"):
        return None
    transfer = query[0]

    def completed(rows: int) -> None:
        transfer.rows = (transfer.rows or 0) + rows

    return completed


def count_query(func: _F) -> _F:
    """Scope a format dispatcher whose first argument is the payload SQL."""

    @wraps(func)
    def wrapped(sql: str, *args: Any, **kwargs: Any) -> Any:
        with payload_query(sql):
            return func(sql, *args, **kwargs)

    return cast(_F, wrapped)


def _fields(operation: str, name: str, args: dict[str, Any]) -> dict[str, str]:
    pool = state.dbs
    alias = pool.current_alias() if pool is not None and pool.current_db is not None else "current"

    def table(schema: Any, table_name: Any, db: Any = alias) -> str:
        return f"{db}:" + (f"{schema}." if schema else "") + str(table_name or "matching sheets")

    if operation == "COPY":
        source = (
            "query on " + str(args["alias1"])
            if "query" in args
            else table(args.get("schema1"), args.get("table1"), args["alias1"])
        )
        destination = table(
            args.get("schema2", args.get("schema")),
            args.get("table2", args.get("table")),
            args["alias2"],
        )
    elif operation == "IMPORT":
        source = str(args["filename"])
        if args.get("sheetname"):
            source += " sheet " + str(args["sheetname"])
        if args.get("patn"):
            source += " sheets matching " + str(args["patn"])
        destination = table(args.get("schema"), args.get("table"))
    else:
        source = (
            "export metadata"
            if "metadata" in name
            else (
                "query on " + alias
                if "query" in args
                else table(args.get("schema"), args.get("tables", args.get("table")))
            )
        )
        if "filename" in args:
            destination = str(args["filename"])
            root = state.conf.export_output_dir
            if root and destination.lower() != "stdout":
                destination = str(Path(root) / destination)
            if args.get("zipfilename"):
                archive = str(args["zipfilename"])
                if root:
                    archive = str(Path(root) / archive)
                destination = archive + " member " + str(args["filename"])
        else:
            destination = table(args.get("schema"), args.get("table"))
    last = state.last_command
    fields = {"source": source, "destination": destination}
    if last is not None:
        fields["at"] = f"{last.source}:{last.line_no}"
    if args.get("format"):
        fields["format"] = str(args["format"]).lower()
    if args.get("new"):
        fields["mode"] = str(args["new"]).lower()
    elif args.get("append"):
        fields["mode"] = "append"
    return fields


def log_transfer(operation: str) -> Callable[[_F], _F]:
    """Log one started and one terminal event around an actual transfer handler."""

    def decorate(func: _F) -> _F:
        @wraps(func)
        def wrapped(**kwargs: Any) -> Any:
            logger = state.exec_log
            # Library runs without a real log should incur no counting work.
            from execsql.utils.fileio import Logger

            if not isinstance(logger, Logger):
                return func(**kwargs)
            fields = _fields(operation, func.__name__, kwargs)
            count_name = "rows_read" if operation == "EXPORT" and "filename" in kwargs else "rows_loaded"
            transfer = _Transfer(operation, logger, fields, count_name, time.monotonic())
            logger.log_transfer(operation, "started", fields)
            token = _active.set(transfer)
            try:
                try:
                    result = func(**kwargs)
                except BaseException as exc:
                    from execsql.exceptions import ScriptExit

                    # Match the executor: cancellation/timeouts may use a
                    # non-Exception BaseException, not just KeyboardInterrupt.
                    outcome = "failed" if isinstance(exc, (Exception, ScriptExit)) else "interrupted"
                    # Partial counts do not prove that rows were retained or written.
                    transfer.finish(outcome)
                    raise
                if func.__name__ == "x_import_file":
                    transfer.rows = 1
                transfer.finish("completed")
                return result
            finally:
                _active.reset(token)

        return cast(_F, wrapped)

    return decorate
