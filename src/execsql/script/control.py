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

    def __init__(self) -> None:
        self.batchlevels: list[BatchLevels.Batch] = []

    def in_batch(self) -> bool:
        """Return True if execution is currently inside at least one BATCH block."""
        return len(self.batchlevels) > 0

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
        """Commit all databases in the innermost batch level and pop the stack."""
        b = self.batchlevels.pop()
        for db in b.dbs_used:
            db.commit()
