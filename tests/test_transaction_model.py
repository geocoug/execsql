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
- ``ERROR_HALT`` and ``METACOMMAND_ERROR_HALT``, on or off for the whole
  script, and an ``ON ERROR_HALT`` script that stores a row of its own or none.

After each script the rows stored, the run's success, the number of errors
reported and, if the script ran to its end, ``SQL_ERROR()`` must be what the
model predicts.  On a mismatch Hypothesis shrinks the script to the shortest
one that still differs: that script is the bug report.

The rules modelled are the CLAUDE.md decisions "Batches left early" (#121),
"Batch rules" (#125) and #135's "a failed commit is rolled back", with the
documented behavior of nested batches: an inner END BATCH commits everything
pending on its connection, the outer batch's statements included
(docs/reference/metacommands.md, "BEGIN BATCH and END BATCH").  SQLite
throws away uncommitted work when the run closes the connection, so what a
halt rolls back shows only through the ON ERROR_HALT script's commit.

Not modelled: interrupts (#139), and a batch spanning two databases (one
commit failing after another succeeded); hand-written tests cover those.

Each run tries 500 new scripts, plus the fixed examples below;
``EXECSQL_MODEL_EXAMPLES=5000`` tries more.
"""

from __future__ import annotations

import contextlib
import itertools
import os
import sqlite3
import tempfile
from dataclasses import dataclass, field

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

from execsql import run

# ---------------------------------------------------------------------------
# Scripts
# ---------------------------------------------------------------------------

#: Operations that are statements or metacommands (leaves of the script),
#: repeated to weight them: HALT ends the script, so it is rare.
_ANYWHERE = ["ok"] * 6 + ["fail_exec"] * 2 + ["fail_commit"] * 2 + ["meta_fail"] * 2 + ["halt"]
_IN_BATCH = ["rollback_batch"] * 2
_IN_LOOP = ["break"] * 2
_AUTOCOMMIT = ["autocommit_off", "autocommit_on", "autocommit_on_commit", "autocommit_on_rollback"]
_MAX_DEPTH = 3


def _body(depth: int, in_batch: bool, in_loop: bool) -> st.SearchStrategy[list]:
    """A list of operations; a batch is a list, a loop a ``("loop", list)``."""
    leaves = st.sampled_from(_ANYWHERE + (_IN_BATCH if in_batch else []) + (_IN_LOOP if in_loop else []))
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
    st.lists(_segment, min_size=1, max_size=4).map(
        lambda segments: [op for switch, body in segments for op in ([switch] if switch else []) + body],
    ),
)


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
                nodes.append((op, next(values) if op in ("ok", "fail_commit") else None, None))
        return nodes

    return walk(ops)


_LINES = {
    "ok": "insert into t values ({n});",
    "fail_exec": "insert into no_such_table values (1);",
    "fail_commit": "insert into child values ({n});",
    "meta_fail": "-- !x! CD {missing_dir}",
    "halt": "-- !x! HALT",
    "rollback_batch": "-- !x! ROLLBACK BATCH",
    "break": "-- !x! BREAK",
    "autocommit_off": "-- !x! AUTOCOMMIT OFF",
    "autocommit_on": "-- !x! AUTOCOMMIT ON",
    "autocommit_on_commit": "-- !x! AUTOCOMMIT ON WITH COMMIT",
    "autocommit_on_rollback": "-- !x! AUTOCOMMIT ON WITH ROLLBACK",
}


def _render(script: tuple, nodes: list, tmp: str) -> str:
    error_halt, metacommand_halt, handler, _ = script
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
    autocommit: bool = True
    #: Rows stored, as (table, value).
    committed: list = field(default_factory=list)
    #: Rows run but not committed on the connection.
    pending: list = field(default_factory=list)
    batches: list = field(default_factory=list)
    errors: int = 0
    sql_error: bool = False
    #: Whether the script ran to its end.
    finished: bool = False

    def run(self, nodes: list) -> None:
        try:
            self._body(nodes)
            self.finished = True
        except _Halted as halt:
            # exit_now abandons every open batch, then runs ON ERROR_HALT.
            while self.batches:
                self._abandon_batch()
            if halt.error and self.handler:
                self.pending.append(("log", 1))
                # Its commit also commits what plain AUTOCOMMIT ON left held,
                # and fails on a row that cannot be committed.  That failure
                # is reported only under ERROR_HALT OFF (the run is already
                # halting).
                if self.autocommit and not self._commit() and not self.error_halt:
                    self.errors += 1
        # The run closes the connection: what was never committed is lost.
        self.pending.clear()

    # -- the connection --------------------------------------------------

    def _commit(self) -> bool:
        """Commit everything pending; a failed commit rolls it all back (#135)."""
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

    def _statement(self, row: tuple) -> None:
        self.sql_error = False
        if self.batches:
            self.batches[-1].used = True
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
)


def _stored(db: str) -> list:
    with contextlib.closing(sqlite3.connect(db)) as conn:
        return sorted(
            [("t", n) for (n,) in conn.execute("select n from t")]
            + [("log", n) for (n,) in conn.execute("select n from log")]
            + [("child", n) for (n,) in conn.execute("select pid from child")],
        )


# Combinations generated scripts reach too rarely to rely on, run every time.
# Work held under AUTOCOMMIT OFF, ended by a failed statement, by AUTOCOMMIT
# ON WITH ROLLBACK, by plain AUTOCOMMIT ON, or by a failed batch:
@example((False, False, False, ["autocommit_off", "ok", "fail_exec", "autocommit_on_commit"]))
@example((False, False, False, ["autocommit_off", "ok", "autocommit_on_rollback", "ok"]))
@example((False, False, False, ["autocommit_off", "ok", "autocommit_on", "ok"]))
@example((False, False, False, ["autocommit_off", "ok", "autocommit_on", "fail_exec"]))
@example((False, False, False, ["autocommit_off", ["ok", "meta_fail"], "autocommit_on_commit"]))
# AUTOCOMMIT ON WITH COMMIT whose commit fails is a metacommand error:
@example((True, False, False, ["autocommit_off", "fail_commit", "autocommit_on_commit", "ok"]))
# An inner END BATCH commits the outer batch's statements before the outer one fails:
@example((False, False, False, [["ok", ["ok"], "fail_exec"]]))
@example((False, False, False, [["ok", ["ok"], "meta_fail"], "ok"]))
# A halt inside a batch rolls it back before the ON ERROR_HALT script commits:
@example((False, True, True, [["ok", "meta_fail"]]))
# ... whose commit also commits what plain AUTOCOMMIT ON left held, and can fail:
@example((False, True, True, ["autocommit_off", "fail_commit", "autocommit_on", "meta_fail"]))
# BREAK leaves the batches inside the loop: rolled back, or joining the one around it:
@example((False, False, False, [("loop", [["ok", "break"]]), "ok"]))
@example((False, False, False, [["ok", ("loop", [["ok", "break"]]), "ok"]]))
# A failure marks every enclosing batch, not only the innermost:
@example((False, False, False, [["ok", ("loop", [["meta_fail", "break"]]), "ok"]]))
# ROLLBACK BATCH rolls back only a batch that used the connection:
@example((False, False, False, [["ok", ["rollback_batch"]]]))
# END BATCH clears SQL_ERROR():
@example((False, False, False, ["fail_exec", []]))
@given(scripts)
@settings(
    max_examples=int(os.environ.get("EXECSQL_MODEL_EXAMPLES", "500")),
    deadline=None,
    # New scripts on every run, CI included (Hypothesis's CI profile would
    # repeat one fixed sample); a failure prints the script that differs.
    derandomize=False,
    database=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_the_stored_rows_and_errors_match_the_model(script):
    error_halt, metacommand_halt, handler, ops = script
    nodes = _number(ops)
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "t.db")
        sql = _render(script, nodes, tmp)
        result = run(sql=_SETUP + sql, dsn=f"sqlite:///{db}", new_db=True)
        stored = _stored(db)
        sql_error = os.path.exists(os.path.join(tmp, "sql_error.txt"))
    model = _Model(error_halt, metacommand_halt, handler)
    model.run(nodes)
    assert (stored, len(result.errors)) == (sorted(model.committed), model.errors), sql
    assert result.success is (model.errors == 0), sql
    if model.finished:
        assert sql_error is model.sql_error, sql
