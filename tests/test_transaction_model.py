"""The transaction rules, checked against generated scripts (#142).

Every recent transaction bug was a combination nobody had written a test
for.  Here the rules are written once, as a small model of one SQLite
connection, and Hypothesis generates scripts from these operations:

- an insert that succeeds;
- an insert that fails as it runs (no such table);
- an insert that fails at COMMIT (a deferred foreign key with no parent row);
- a metacommand that fails without touching the database (CD to a missing directory);
- ``BEGIN BATCH`` / ``END BATCH``, nested;
- ``ROLLBACK BATCH``;
- a ``LOOP`` that runs once, and ``BREAK`` inside it;
- ``AUTOCOMMIT OFF`` / ``ON`` / ``ON WITH COMMIT`` / ``ON WITH ROLLBACK``, outside batches;
- ``HALT``;
- an interrupt (#139) right after an insert ran, in a metacommand after it
  wrote (``EXECUTE``), at entry to ``Database.commit()`` before its rollback
  handler, or just after the driver's next commit on the connection;
- ``ERROR_HALT`` and ``METACOMMAND_ERROR_HALT``, on or off for the whole
  script, an ``ON ERROR_HALT`` script that stores a row of its own or none,
  and whether interrupts are ``KeyboardInterrupt`` (raised out of ``run()``)
  or a plain ``SystemExit`` (a signal handler's, such as the one the
  ``execsql`` command installs for SIGTERM: ``run()`` returns a failed
  result).

The script runs on the test's own connection, as ``execsql.run(connection=)``
does for a caller that keeps it, and the interrupts come from that
connection.  After each script the rows stored, the rows still pending on
the connection, how the run ended, the number of errors reported and, if the
script ran to its end, ``SQL_ERROR()`` must be what the model predicts.  On a
mismatch Hypothesis shrinks the script to the shortest one that still
differs: that script is the bug report.

The rules modelled are the AGENTS.md decisions "Batches left early" (#121),
"Batch rules" (#125) and #135's "a failed commit is rolled back", with the
documented behavior of nested batches: an inner END BATCH commits everything
pending on its connection, the outer batch's statements included
(docs/reference/metacommands.md, "BEGIN BATCH and END BATCH"), and
"Interrupted statements" (#139).

Not modelled: a batch spanning two databases (one commit failing after
another succeeded), and an interrupt at a BREAKPOINT prompt, where the run
carries on; hand-written tests cover those.

Each run tries 700 new scripts, plus the fixed examples below;
``EXECSQL_MODEL_EXAMPLES=5000`` tries more.
"""

from __future__ import annotations

import contextlib
import functools
import itertools
import os
import re
import sqlite3
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from unittest.mock import patch

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

from execsql import run
from execsql.db.base import Database
from execsql.db.sqlite import SQLiteDatabase

# ---------------------------------------------------------------------------
# Scripts
# ---------------------------------------------------------------------------

#: Operations that are statements or metacommands (leaves of the script),
#: repeated to weight them: HALT ends the script, so it is rare.
_ANYWHERE = ["ok"] * 6 + ["fail_exec"] * 2 + ["fail_commit"] * 2 + ["meta_fail"] * 2 + ["halt"]
#: The interrupts also end the script: together they weigh what HALT does.
_INTERRUPTS = ["interrupt_sql", "interrupt_meta", "interrupt_before_commit", "interrupt_after_commit"]
_IN_BATCH = ["rollback_batch"] * 2
_IN_LOOP = ["break"] * 2
_AUTOCOMMIT = ["autocommit_off", "autocommit_on", "autocommit_on_commit", "autocommit_on_rollback"]
_MAX_DEPTH = 3


def _body(depth: int, in_batch: bool, in_loop: bool) -> st.SearchStrategy[list]:
    """A list of operations; a batch is a list, a loop a ``("loop", list)``."""
    plain = _ANYWHERE + (_IN_BATCH if in_batch else []) + (_IN_LOOP if in_loop else [])
    # Each other leaf once per interrupt, so the interrupts together weigh one leaf.
    leaves = st.sampled_from(plain * len(_INTERRUPTS) + _INTERRUPTS)
    if depth < _MAX_DEPTH:
        batch = st.deferred(lambda: _body(depth + 1, True, in_loop))
        loop = st.deferred(lambda: _body(depth + 1, in_batch, True)).map(lambda body: ("loop", body))
        # One item in five is a batch, one in ten a loop.
        leaves = st.one_of(*[leaves] * 7, batch, batch, loop)
    return st.lists(leaves, min_size=0 if depth else 1, max_size=5)


# A script is a few segments, each an AUTOCOMMIT metacommand (or none) and
# the work after it, so that work held under AUTOCOMMIT OFF meets each way
# of ending it (ON, ON WITH COMMIT, ON WITH ROLLBACK, a failure, a batch).
_segment = st.tuples(st.sampled_from([None, *_AUTOCOMMIT]), _body(0, False, False))
scripts = st.tuples(
    st.booleans(),  # ERROR_HALT
    st.booleans(),  # METACOMMAND_ERROR_HALT
    st.booleans(),  # an ON ERROR_HALT script
    st.booleans(),  # interrupts are a plain SystemExit, not KeyboardInterrupt
    st.lists(_segment, min_size=1, max_size=4).map(
        lambda segments: [op for switch, body in segments for op in ([switch] if switch else []) + body],
    ),
)


#: Operations that store a row of their own.
_NUMBERED = ("ok", "fail_commit", "interrupt_sql", "interrupt_meta")


def _number(ops: list) -> list:
    """*ops* as ``(kind, n, body)`` nodes: each insert gets its value, each loop its counter."""
    values, loops = itertools.count(1), itertools.count(1)

    def walk(items: list) -> list:
        nodes = []
        for op in items:
            if isinstance(op, list):
                nodes.append(("batch", None, walk(op)))
            elif isinstance(op, tuple):
                nodes.append(("loop", next(loops), walk(op[1])))
            else:
                nodes.append((op, next(values) if op in _NUMBERED else None, None))
        return nodes

    return walk(ops)


_LINES = {
    "ok": "insert into t values ({n});",
    "fail_exec": "insert into no_such_table values (1);",
    "fail_commit": "insert into child values ({n});",
    "meta_fail": "-- !x! CD {missing_dir}",
    "halt": "-- !x! HALT",
    # _Connection raises the interrupts these ask for.
    "interrupt_sql": "insert into interrupted values ({n});",
    "interrupt_meta": "-- !x! EXECUTE interrupt_{n}",
    "interrupt_before_commit": "select 'interrupt before the next commit';",
    "interrupt_after_commit": "select 'interrupt after the next commit';",
    "rollback_batch": "-- !x! ROLLBACK BATCH",
    "break": "-- !x! BREAK",
    "autocommit_off": "-- !x! AUTOCOMMIT OFF",
    "autocommit_on": "-- !x! AUTOCOMMIT ON",
    "autocommit_on_commit": "-- !x! AUTOCOMMIT ON WITH COMMIT",
    "autocommit_on_rollback": "-- !x! AUTOCOMMIT ON WITH ROLLBACK",
}


def _render(script: tuple, nodes: list, tmp: str) -> str:
    error_halt, metacommand_halt, handler, _, _ = script
    lines = [
        f"-- !x! ERROR_HALT {'ON' if error_halt else 'OFF'}",
        f"-- !x! METACOMMAND_ERROR_HALT {'ON' if metacommand_halt else 'OFF'}",
    ]
    if handler:
        lines += [
            "-- !x! BEGIN SCRIPT on_halt",
            "insert into log values (1);",
            "-- !x! END SCRIPT",
            "-- !x! ON ERROR_HALT EXECUTE SCRIPT on_halt",
        ]

    def emit(items: list) -> None:
        for kind, n, body in items:
            if kind == "batch":
                lines.append("-- !x! BEGIN BATCH")
                emit(body)
                lines.append("-- !x! END BATCH")
            elif kind == "loop":
                lines.extend(
                    [
                        f"-- !x! SUB loop{n} 0",
                        f"-- !x! LOOP WHILE (IS_GT(1, !!loop{n}!!))",
                        f"-- !x! SUB_ADD loop{n} 1",
                    ],
                )
                emit(body)
                lines.append("-- !x! END LOOP")
            else:
                lines.append(_LINES[kind].format(n=n, missing_dir=os.path.join(tmp, "no_such_dir")))

    emit(nodes)
    # Reached only if the script runs to its end.
    lines.append(f'-- !x! IF (SQL_ERROR()) {{ WRITE "1" TO {os.path.join(tmp, "sql_error.txt")} }}')
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------


class _Halted(Exception):
    def __init__(self, error: bool) -> None:
        self.error = error


class _Break(Exception):
    pass


class _Interrupted(Exception):
    pass


@dataclass
class _Batch:
    failed: bool = False
    #: Whether an SQL statement ran in it, so END BATCH commits its database.
    used: bool = False


@dataclass
class _Model:
    error_halt: bool
    metacommand_halt: bool
    handler: bool
    #: Whether interrupts are a plain SystemExit (else KeyboardInterrupt).
    sigterm: bool
    autocommit: bool = True
    #: Whether the next commit on the connection is interrupted, "before" or
    #: "after" the driver commits.
    armed: str | None = None
    #: Rows stored, as (table, value).
    committed: list = field(default_factory=list)
    #: Rows run but not committed on the connection.
    pending: list = field(default_factory=list)
    batches: list = field(default_factory=list)
    errors: int = 0
    sql_error: bool = False
    #: Whether the script ran to its end.
    finished: bool = False
    #: Whether an interrupt ended the run (raised out of run() unless sigterm).
    interrupted: bool = False

    def run(self, nodes: list) -> None:
        halting = False
        try:
            try:
                self._body(nodes)
                self.finished = True
            except _Halted as halt:
                halting = True
                # exit_now abandons every open batch, then runs ON ERROR_HALT.
                self._abandon_all()
                if halt.error and self.handler:
                    self.pending.append(("log", 1))
                    # Its commit also commits what plain AUTOCOMMIT ON left
                    # held, and fails on a row that cannot be committed.  That
                    # failure is reported only under ERROR_HALT OFF (the run
                    # is already halting).
                    if self.autocommit and not self._commit() and not self.error_halt:
                        self.errors += 1
        except _Interrupted:
            # The interrupt leaves every open batch on its way out of run().
            self.interrupted = True
            self._abandon_all()
            # A SystemExit is reported as the error that ended the run,
            # unless a halt's error already is (an interrupted ON ERROR_HALT
            # script).
            if self.sigterm and not halting:
                self.errors += 1
        # What is left pending stays on the caller's connection.

    # -- the connection --------------------------------------------------

    def _commit(self) -> bool:
        """Commit everything pending; a failed commit rolls it all back (#135)."""
        if self.armed is not None:
            # Interrupted before the commit: the enclosing statement, batch,
            # or run rolls back. After the driver committed, nothing can undo it.
            if self.armed == "after" and not any(table == "child" for table, _ in self.pending):
                self.committed += self.pending
            self.armed = None
            self.pending.clear()
            raise _Interrupted
        if any(table == "child" for table, _ in self.pending):
            self.pending.clear()
            return False
        self.committed += self.pending
        self.pending.clear()
        return True

    # -- failures ---------------------------------------------------------

    def _fail_batches(self) -> None:
        for batch in self.batches:
            batch.failed = True

    def _sql_failed(self) -> None:
        self.errors += 1
        self.sql_error = True
        self._fail_batches()
        if self.error_halt:
            raise _Halted(error=True)

    def _metacommand_failed(self) -> None:
        self.errors += 1
        self._fail_batches()
        if self.metacommand_halt:
            raise _Halted(error=True)

    # -- operations -------------------------------------------------------

    def _body(self, nodes: list) -> None:
        for kind, n, body in nodes:
            if kind == "batch":
                self._batch(body)
            elif kind == "loop":
                self._loop(body)
            elif n is not None:
                getattr(self, f"_{kind}")(n)
            else:
                getattr(self, f"_{kind}")()

    def _statement(self, row: tuple | None) -> None:
        self.sql_error = False
        if self.batches:
            self.batches[-1].used = True
        if row is not None:
            self.pending.append(row)
        if not self.batches and self.autocommit and not self._commit():
            self._sql_failed()

    def _ok(self, n: int) -> None:
        self._statement(("t", n))

    def _fail_commit(self, n: int) -> None:
        self._statement(("child", n))

    def _fail_exec(self) -> None:
        if self.batches:
            self.batches[-1].used = True
        self.pending.clear()  # Database.execute() rolls back on an error
        self._sql_failed()

    def _meta_fail(self) -> None:
        self._metacommand_failed()

    def _halt(self) -> None:
        self.errors += 1  # "Script halted by HALT"
        raise _Halted(error=False)

    def _break(self) -> None:
        raise _Break

    # An interrupted statement or metacommand is a failed one (#139): it
    # fails the open batches and sets SQL_ERROR(), which nothing can see
    # once the interrupt has ended the run.

    def _interrupt_sql(self, n: int) -> None:
        # Interrupted after the insert ran: the connection is rolled back
        # whatever AUTOCOMMIT says, as for a failed statement.
        self.pending.clear()
        raise _Interrupted

    def _interrupt_meta(self, n: int) -> None:
        # EXECUTE wrote, then was interrupted: a connection with autocommit on
        # is rolled back; under AUTOCOMMIT OFF the write joins what the
        # script holds, which the script (here, the caller) decides.
        if self.autocommit:
            self.pending.clear()
        else:
            self.pending.append(("interrupted", n))
        raise _Interrupted

    # A statement that stores nothing; the next commit is interrupted.

    def _interrupt_before_commit(self) -> None:
        self.armed = "before"
        self._statement(None)

    def _interrupt_after_commit(self) -> None:
        self.armed = "after"
        self._statement(None)

    def _rollback_batch(self) -> None:
        if self.batches[-1].used:
            self.pending.clear()

    def _autocommit_off(self) -> None:
        self.autocommit = False

    def _autocommit_on(self) -> None:
        self.autocommit = True  # what was held waits for the next commit

    def _autocommit_on_commit(self) -> None:
        self.autocommit = True
        if not self._commit():
            self._metacommand_failed()

    def _autocommit_on_rollback(self) -> None:
        self.autocommit = True
        self.pending.clear()

    def _abandon_batch(self) -> None:
        """Leave the innermost batch without END BATCH (#121): a nested
        batch's work joins the enclosing one; the outermost is rolled back,
        except under AUTOCOMMIT OFF, where the transaction is the script's."""
        batch = self.batches.pop()
        if self.batches:
            self.batches[-1].used |= batch.used
        elif batch.used and self.autocommit:
            self.pending.clear()

    def _abandon_all(self) -> None:
        while self.batches:
            self._abandon_batch()

    def _batch(self, body: list) -> None:
        self.batches.append(_Batch())
        depth = len(self.batches)
        try:
            self._body(body)
        except _Break:
            while len(self.batches) >= depth:
                self._abandon_batch()
            raise
        if any(b.failed for b in self.batches):
            # Not committed: abandoned as if left early, then END BATCH
            # reports an SQL error (#125).
            self._abandon_batch()
            self._sql_failed()
            return
        # END BATCH commits everything pending on the connection, an
        # enclosing batch's statements included.
        batch = self.batches.pop()
        self.sql_error = False
        if batch.used and self.autocommit and not self._commit():
            self._sql_failed()

    def _loop(self, body: list) -> None:
        with contextlib.suppress(_Break):
            self._body(body)


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------

_SETUP = (
    "PRAGMA foreign_keys = ON;\n"
    "create table t (n integer);\n"
    "create table log (n integer);\n"
    "create table parent (id integer primary key);\n"
    "create table child (pid integer references parent(id) deferrable initially deferred);\n"
    "create table interrupted (n integer);\n"
)


def _rows(conn: sqlite3.Connection) -> list:
    return sorted(
        [(table, n) for table in ("t", "log", "interrupted") for (n,) in conn.execute(f"select n from {table}")]
        + [("child", n) for (n,) in conn.execute("select pid from child")],
    )


class _Cursor:
    """A cursor that raises the interrupts the script's statements ask for."""

    def __init__(self, curs: sqlite3.Cursor, conn: _Connection) -> None:
        self._curs = curs
        self._conn = conn

    def execute(self, sql: str, *args: object) -> sqlite3.Cursor:
        if m := re.fullmatch(r'select \* from "interrupt_(\d+)";', sql):
            # EXECUTE interrupt_<n>: write, then be interrupted.
            self._curs.execute(f"insert into interrupted values ({m[1]})")
            raise self._conn.interrupt()
        result = self._curs.execute(sql, *args)
        if sql.startswith("insert into interrupted"):
            raise self._conn.interrupt()  # after the statement ran
        if m := re.fullmatch(r"select 'interrupt (before|after) the next commit';", sql):
            self._conn.armed = m[1]
        return result

    def __getattr__(self, name: str) -> object:
        return getattr(self._curs, name)


class _Connection:
    """The caller's sqlite3 connection, injecting selected driver-boundary interrupts.

    Raises immediately after an insert or EXECUTE writes, or after the driver
    commit returns. The test injects the "before" case separately, at entry to
    Database.commit(), outside that method's rollback handler. These selected
    boundaries do not cover arbitrary Python lines, rollback calls, or
    BREAKPOINT input; the latter has separate hand-written tests.
    """

    def __init__(self, conn: sqlite3.Connection, interrupt: Callable[[], BaseException]) -> None:
        self._conn = conn
        self.interrupt = interrupt
        self.armed: str | None = None

    def cursor(self) -> _Cursor:
        return _Cursor(self._conn.cursor(), self)

    def commit(self) -> None:
        when, self.armed = self.armed, None
        if when is None:
            self._conn.commit()
            return
        assert when == "after"  # "before" is consumed at Database.commit() entry
        # The interrupt lands as the driver returns, whether it committed or failed.
        with contextlib.suppress(sqlite3.Error):
            self._conn.commit()
        raise self.interrupt()

    def __getattr__(self, name: str) -> object:
        return getattr(self._conn, name)


# Combinations generated scripts reach too rarely to rely on, run every time.
# A failed commit must not drag a later statement or ON ERROR_HALT's writes
# into the failed transaction (#135):
@example((False, False, False, False, ["fail_commit", "ok"]))
@example((True, True, True, False, ["fail_commit"]))
# Work held under AUTOCOMMIT OFF, ended by a failed statement, by AUTOCOMMIT
# ON WITH ROLLBACK, by plain AUTOCOMMIT ON, or by a failed batch:
@example((False, False, False, False, ["autocommit_off", "ok", "fail_exec", "autocommit_on_commit"]))
@example((False, False, False, False, ["autocommit_off", "ok", "autocommit_on_rollback", "ok"]))
@example((False, False, False, False, ["autocommit_off", "ok", "autocommit_on", "ok"]))
@example((False, False, False, False, ["autocommit_off", "ok", "autocommit_on", "fail_exec"]))
@example((False, False, False, False, ["autocommit_off", ["ok", "meta_fail"], "autocommit_on_commit"]))
# AUTOCOMMIT ON WITH COMMIT whose commit fails is a metacommand error:
@example((True, False, False, False, ["autocommit_off", "fail_commit", "autocommit_on_commit", "ok"]))
# An inner END BATCH commits the outer batch's statements before the outer one fails:
@example((False, False, False, False, [["ok", ["ok"], "fail_exec"]]))
@example((False, False, False, False, [["ok", ["ok"], "meta_fail"], "ok"]))
# A halt inside a batch rolls it back before the ON ERROR_HALT script commits:
@example((False, True, True, False, [["ok", "meta_fail"]]))
# ... whose commit also commits what plain AUTOCOMMIT ON left held, and can fail:
@example((False, True, True, False, ["autocommit_off", "fail_commit", "autocommit_on", "meta_fail"]))
@example((True, True, True, False, ["autocommit_off", "fail_commit", "autocommit_on", "meta_fail"]))
# BREAK leaves the batches inside the loop: rolled back, or joining the one around it:
@example((False, False, False, False, [("loop", [["ok", "break"]]), "ok"]))
@example((False, False, False, False, [["ok", ("loop", [["ok", "break"]]), "ok"]]))
# A failure marks every enclosing batch, not only the innermost:
@example((False, False, False, False, [["ok", ("loop", [["meta_fail", "break"]]), "ok"]]))
@example((False, False, False, False, [["ok", ["fail_exec"], "ok"]]))
# ROLLBACK BATCH does not recover a batch with a failed statement:
@example((False, False, False, False, [["fail_exec", "rollback_batch", "ok"]]))
# ROLLBACK BATCH rolls back only a batch that used the connection:
@example((False, False, False, False, [["ok", ["rollback_batch"]]]))
# END BATCH clears SQL_ERROR():
@example((False, False, False, False, ["fail_exec", []]))
# An interrupted statement rolls back what AUTOCOMMIT OFF held; an
# interrupted metacommand leaves it (and its own write) to the script, but
# rolls back what plain AUTOCOMMIT ON left held:
@example((False, False, False, False, ["autocommit_off", "ok", "interrupt_sql"]))
@example((False, False, False, False, ["autocommit_off", "ok", "interrupt_meta"]))
@example((False, False, False, False, ["autocommit_off", "ok", "autocommit_on", "interrupt_meta"]))
# END BATCH interrupted before Database.commit() can roll back (#150), or
# after the driver committed, when nothing can undo it:
@example((False, False, False, False, [["ok", "interrupt_before_commit"]]))
@example((False, False, False, False, [["ok", "interrupt_after_commit"]]))
@example((False, False, False, False, [["fail_commit", "interrupt_after_commit"]]))
# A plain SystemExit inside a batch is reported, not raised:
@example((False, False, False, True, [["ok", "interrupt_sql"]]))
# The ON ERROR_HALT script's commit interrupted, reported as the halt's error or raised:
@example((False, True, True, True, ["autocommit_off", "interrupt_before_commit", "autocommit_on", "meta_fail"]))
@example((False, True, True, False, ["autocommit_off", "interrupt_after_commit", "autocommit_on", "meta_fail"]))
@given(scripts)
@settings(
    max_examples=int(os.environ.get("EXECSQL_MODEL_EXAMPLES", "700")),
    deadline=None,
    # New scripts on every run, CI included (Hypothesis's CI profile would
    # repeat one fixed sample); a failure prints the script that differs.
    derandomize=False,
    database=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_the_stored_rows_and_errors_match_the_model(script):
    error_halt, metacommand_halt, handler, sigterm, ops = script
    nodes = _number(ops)
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "t.db")
        sql = _render(script, nodes, tmp)
        caller = SQLiteDatabase(db)
        caller.conn = _Connection(caller.conn, functools.partial(SystemExit, 143) if sigterm else KeyboardInterrupt)
        real_commit = Database.commit

        def commit(self):
            if self is caller and self.autocommit and caller.conn.armed == "before":
                caller.conn.armed = None
                raise caller.conn.interrupt()
            return real_commit(self)

        try:
            with patch.object(Database, "commit", commit):
                try:
                    result = run(sql=_SETUP + sql, connection=caller)
                except KeyboardInterrupt:
                    result = None
            with contextlib.closing(sqlite3.connect(db)) as other:
                stored = _rows(other)
            held = _rows(caller.conn._conn)
        finally:
            caller.conn._conn.close()  # Windows cannot delete an open database
        sql_error = os.path.exists(os.path.join(tmp, "sql_error.txt"))
    model = _Model(error_halt, metacommand_halt, handler, sigterm)
    model.run(nodes)
    assert stored == sorted(model.committed), sql
    assert held == sorted(model.committed + model.pending), sql
    if model.interrupted and not sigterm:
        assert result is None, sql  # KeyboardInterrupt left run()
        return
    assert result is not None, sql
    assert len(result.errors) == model.errors, sql
    assert result.success is (model.errors == 0), sql
    if model.finished:
        assert sql_error is model.sql_error, sql
