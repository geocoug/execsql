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
- ``AUTOCOMMIT OFF`` / ``ON`` / ``ON WITH COMMIT`` / ``ON WITH ROLLBACK``, outside batches;
- ``HALT``;
- ``ERROR_HALT`` and ``METACOMMAND_ERROR_HALT``, on or off for the whole script.

After each script the rows stored, the run's success and the number of
errors reported must be what the model predicts.  On a mismatch Hypothesis
shrinks the script to the shortest one that still differs: that script is
the bug report.

The rules modelled are the CLAUDE.md decisions "Batches left early" (#121),
"Batch rules" (#125) and #135's "a failed commit is rolled back", with the
documented behavior of nested batches: an inner END BATCH commits everything
pending on its connection, the outer batch's statements included
(docs/reference/metacommands.md, "BEGIN BATCH and END BATCH").

Interrupts (#139) are not modelled yet.  ``HYPOTHESIS_PROFILE=thorough`` runs
thousands of examples instead of the default 500.
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
import tempfile
from dataclasses import dataclass, field

from hypothesis import HealthCheck, settings
from hypothesis import example, given
from hypothesis import strategies as st

from execsql import run

settings.register_profile(
    "default",
    max_examples=500,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.register_profile(
    "thorough",
    max_examples=5000,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))

# ---------------------------------------------------------------------------
# Scripts
# ---------------------------------------------------------------------------

#: Operations that are statements or metacommands (leaves of the script),
#: repeated to weight them: HALT ends the script, so it is rare.
_ANYWHERE = ["ok"] * 6 + ["fail_exec"] * 2 + ["fail_commit"] * 2 + ["meta_fail"] * 2 + ["halt"]
_INSIDE_BATCHES = ["rollback_batch"] * 2
_AUTOCOMMIT = ["autocommit_off", "autocommit_on", "autocommit_on_commit", "autocommit_on_rollback"]
_MAX_DEPTH = 3


def _body(depth: int) -> st.SearchStrategy[list]:
    """A list of operations; a batch is a list of the operations inside it."""
    leaves = st.sampled_from(_ANYWHERE + (_INSIDE_BATCHES if depth else []))
    if depth < _MAX_DEPTH:
        # One item in five is a batch.
        leaves = st.one_of(leaves, leaves, leaves, leaves, st.deferred(lambda: _body(depth + 1)))
    return st.lists(leaves, min_size=0 if depth else 1, max_size=5)


# A script is a few segments, each an AUTOCOMMIT metacommand (or none) and
# the work after it, so that work held under AUTOCOMMIT OFF meets each way
# of ending it (ON, ON WITH COMMIT, ON WITH ROLLBACK, a failure, a batch).
_segment = st.tuples(st.sampled_from([None, *_AUTOCOMMIT]), _body(0))
scripts = st.tuples(
    st.booleans(),
    st.booleans(),
    st.lists(_segment, min_size=1, max_size=4).map(
        lambda segments: [op for switch, body in segments for op in ([switch] if switch else []) + body],
    ),
)


def _render(error_halt: bool, metacommand_halt: bool, ops: list, missing_dir: str) -> str:
    """The script for *ops*; inserted values are numbered in script order."""
    lines = [
        f"-- !x! ERROR_HALT {'ON' if error_halt else 'OFF'}",
        f"-- !x! METACOMMAND_ERROR_HALT {'ON' if metacommand_halt else 'OFF'}",
    ]
    counter = iter(range(1, 10_000))

    def emit(items: list) -> None:
        for op in items:
            if isinstance(op, list):
                lines.append("-- !x! BEGIN BATCH")
                emit(op)
                lines.append("-- !x! END BATCH")
                continue
            lines.append(
                {
                    "ok": lambda: f"insert into t values ({next(counter)});",
                    "fail_exec": lambda: "insert into no_such_table values (1);",
                    "fail_commit": lambda: f"insert into child values ({next(counter)});",
                    "meta_fail": lambda: f"-- !x! CD {missing_dir}",
                    "halt": lambda: "-- !x! HALT",
                    "rollback_batch": lambda: "-- !x! ROLLBACK BATCH",
                    "autocommit_off": lambda: "-- !x! AUTOCOMMIT OFF",
                    "autocommit_on": lambda: "-- !x! AUTOCOMMIT ON",
                    "autocommit_on_commit": lambda: "-- !x! AUTOCOMMIT ON WITH COMMIT",
                    "autocommit_on_rollback": lambda: "-- !x! AUTOCOMMIT ON WITH ROLLBACK",
                }[op](),
            )

    emit(ops)
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------


class _Halted(Exception):
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
    autocommit: bool = True
    #: Rows stored, as (table, value).
    committed: list = field(default_factory=list)
    #: Rows run but not committed on the connection.
    pending: list = field(default_factory=list)
    batches: list = field(default_factory=list)
    errors: int = 0

    def run(self, ops: list) -> None:
        self._counter = iter(range(1, 10_000))
        try:
            self._body(ops)
        except _Halted:
            pass
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
        self._fail_batches()
        if self.error_halt:
            raise _Halted

    def _metacommand_failed(self) -> None:
        self.errors += 1
        self._fail_batches()
        if self.metacommand_halt:
            raise _Halted

    # -- operations -------------------------------------------------------

    def _body(self, ops: list) -> None:
        for op in ops:
            if isinstance(op, list):
                self._batch(op)
            else:
                getattr(self, f"_{op}")()

    def _statement(self, row: tuple) -> None:
        if self.batches:
            self.batches[-1].used = True
        self.pending.append(row)
        if not self.batches and self.autocommit and not self._commit():
            self._sql_failed()

    def _ok(self) -> None:
        self._statement(("t", next(self._counter)))

    def _fail_commit(self) -> None:
        self._statement(("child", next(self._counter)))

    def _fail_exec(self) -> None:
        if self.batches:
            self.batches[-1].used = True
        self.pending.clear()  # Database.execute() rolls back on an error
        self._sql_failed()

    def _meta_fail(self) -> None:
        self._metacommand_failed()

    def _halt(self) -> None:
        self.errors += 1  # "Script halted by HALT"
        raise _Halted

    def _rollback_batch(self) -> None:
        if self.batches[-1].used:
            self.pending.clear()

    def _autocommit_off(self) -> None:
        self.autocommit = False

    def _autocommit_on(self) -> None:
        self.autocommit = True

    def _autocommit_on_commit(self) -> None:
        self.autocommit = True
        if not self._commit():
            self._metacommand_failed()

    def _autocommit_on_rollback(self) -> None:
        self.autocommit = True
        self.pending.clear()

    def _batch(self, ops: list) -> None:
        self.batches.append(_Batch())
        self._body(ops)  # a halt leaves through here; the run ends
        batch = self.batches.pop()
        if batch.failed or any(b.failed for b in self.batches):
            # Not committed: a nested batch's work joins the enclosing
            # batch; the outermost is rolled back (AUTOCOMMIT OFF: left to
            # the script).  END BATCH then reports an SQL error.
            if self.batches:
                self.batches[-1].used |= batch.used
            elif batch.used and self.autocommit:
                self.pending.clear()
            self._sql_failed()
            return
        # END BATCH commits everything pending on the connection, an
        # enclosing batch's statements included.
        if batch.used and self.autocommit and not self._commit():
            self._sql_failed()


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------

_SETUP = (
    "PRAGMA foreign_keys = ON;\n"
    "create table t (n integer);\n"
    "create table parent (id integer primary key);\n"
    "create table child (pid integer references parent(id) deferrable initially deferred);\n"
)


def _stored(db: str) -> list:
    with contextlib.closing(sqlite3.connect(db)) as conn:
        return sorted(
            [("t", n) for (n,) in conn.execute("select n from t")]
            + [("child", n) for (n,) in conn.execute("select pid from child")],
        )


# Combinations generated scripts reach too rarely to rely on, run every time:
# work held under AUTOCOMMIT OFF and ended by a failed statement, by AUTOCOMMIT
# ON WITH ROLLBACK, and by plain AUTOCOMMIT ON; an inner END BATCH committing
# the outer batch's statements before the outer batch fails.
@example((False, False, ["autocommit_off", "ok", "fail_exec", "autocommit_on_commit"]))
@example((False, False, ["autocommit_off", "ok", "autocommit_on_rollback", "ok"]))
@example((False, False, ["autocommit_off", "ok", "autocommit_on", "ok"]))
@example((False, False, [["ok", ["ok"], "fail_exec"]]))
@example((False, False, [["ok", ["ok"], "meta_fail"], "ok"]))
@given(scripts)
def test_the_stored_rows_and_errors_match_the_model(script):
    error_halt, metacommand_halt, ops = script
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "t.db")
        sql = _render(error_halt, metacommand_halt, ops, os.path.join(tmp, "no_such_dir"))
        result = run(sql=_SETUP + sql, dsn=f"sqlite:///{db}", new_db=True)
        stored = _stored(db)
    model = _Model(error_halt, metacommand_halt)
    model.run(ops)
    assert (stored, len(result.errors)) == (sorted(model.committed), model.errors), sql
    assert result.success is (model.errors == 0), sql
