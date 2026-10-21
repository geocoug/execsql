from __future__ import annotations

"""Control-flow stack structures for execsql script execution.

Classes:
- :class:`BatchLevels` — tracks which databases are used in nested BEGIN/END BATCH blocks.

IF/ELSE/ENDIF condition handling is structural under the AST executor;
the legacy ``IfItem`` / ``IfLevels`` classes were removed.
"""

from typing import Any

__all__ = ["BatchLevels"]


# ---------------------------------------------------------------------------
# BatchLevels
# ---------------------------------------------------------------------------


class BatchLevels:
    """Track the databases used within nested BEGIN/END BATCH blocks.

    Maintains a stack of :class:`Batch` objects so that each nesting level
    records its own set of active database connections for commit/rollback.
    """

    # A stack to keep a record of the databases used in nested batches.
    class Batch:
        def __init__(self) -> None:
            self.dbs_used: list[Any] = []
            # Why this batch can no longer commit (a nested batch's commit
            # failed and rolled back connections it shares), or None.
            self.failed: str | None = None

    def __init__(self) -> None:
        self.batchlevels: list[BatchLevels.Batch] = []

    def in_batch(self) -> bool:
        """Return True if execution is currently inside at least one BATCH block."""
        return len(self.batchlevels) > 0

    def fail_enclosing(self, reason: str) -> None:
        """Mark every open batch level as failed, so its END BATCH rolls back instead of committing."""
        for b in self.batchlevels:
            if b.failed is None:
                b.failed = reason

    def failure(self) -> str | None:
        """Why the innermost batch level can no longer commit, or None."""
        return self.batchlevels[-1].failed if self.batchlevels else None

    def new_batch(self) -> None:
        """Push a new empty batch level onto the stack."""
        self.batchlevels.append(self.Batch())

    def using_db(self, db: Any) -> None:
        """Register *db* as used within the innermost active batch."""
        if len(self.batchlevels) > 0 and db not in self.batchlevels[-1].dbs_used:
            self.batchlevels[-1].dbs_used.append(db)

    def uses_db(self, db: Any) -> bool:
        """Return True if *db* is registered in any active batch level."""
        if len(self.batchlevels) == 0:
            return False
        return any(db in batch.dbs_used for batch in self.batchlevels)

    def rollback_batch(self) -> None:
        """Roll back all databases registered in the innermost batch level."""
        if len(self.batchlevels) > 0:
            b = self.batchlevels[-1]
            for db in b.dbs_used:
                db.rollback()

    def end_batch(self) -> None:
        """Commit all databases in the innermost batch level and pop the stack.

        If a commit fails, that database and the ones not yet committed are
        rolled back (except one with autocommit off, whose transaction is the
        script's) before the error is raised: a commit that already succeeded
        cannot be undone, but nothing else of the batch is left pending for
        a later statement to commit.
        """
        b = self.batchlevels.pop()
        for i, db in enumerate(b.dbs_used):
            try:
                db.commit()
            except BaseException:
                for rest in b.dbs_used[i:]:
                    if rest.autocommit:
                        rest.rollback()
                raise

    def abandon_batch(self) -> None:
        """Pop the innermost batch level without committing it.

        Inside another batch, its databases join the enclosing level, which
        commits or rolls them back.  Otherwise they are rolled back, except
        one with autocommit off: :meth:`end_batch` would not have committed
        it either, so its transaction stays the script's to end.
        """
        b = self.batchlevels.pop()
        if self.batchlevels:
            for db in b.dbs_used:
                self.using_db(db)
            return
        for db in b.dbs_used:
            if db.autocommit:
                db.rollback()

    def abandon_all(self) -> None:
        """Abandon every open batch level, innermost first."""
        while self.batchlevels:
            self.abandon_batch()
