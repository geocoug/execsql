from __future__ import annotations

"""Control-flow stack structures for execsql script execution.

Classes:
- :class:`BatchLevels` — tracks which databases are used in nested BEGIN/END BATCH blocks.
- :class:`IfItem` — one level of a nested IF/ELSE/ENDIF condition.
- :class:`IfLevels` — stack of boolean IF-level states.
"""

from typing import Any

from execsql.exceptions import ErrInfo

__all__ = ["BatchLevels", "IfItem", "IfLevels"]


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


# ---------------------------------------------------------------------------
# IfItem / IfLevels
# ---------------------------------------------------------------------------


class IfItem:
    """One level of a nested IF/ELSE/ENDIF condition, paired with its source location."""

    # An object representing an 'if' level, with context data.
    def __init__(self, tf_value: bool) -> None:
        self.tf_value = tf_value
        # Import from the package (not engine directly) so that test patches on
        # execsql.script.current_script_line are effective.
        from execsql.script import current_script_line

        self.scriptname, self.scriptline = current_script_line()

    def value(self) -> bool:
        return self.tf_value

    def invert(self) -> None:
        self.tf_value = not self.tf_value

    def change_to(self, tf_value: bool) -> None:
        self.tf_value = tf_value

    def script_line(self) -> tuple:
        return (self.scriptname, self.scriptline)


class IfLevels:
    """Stack of boolean IF-level states for nested conditional execution.

    Each :meth:`nest` call corresponds to an IF statement; each
    :meth:`unnest` call corresponds to an ENDIF.  :meth:`all_true` drives
    the execution gate — commands are skipped unless every level is ``True``.
    """

    # A stack of True/False values corresponding to a nested set of conditionals,
    # with methods to manipulate and query the set of conditional states.
    def __init__(self) -> None:
        self.if_levels: list[IfItem] = []

    def nest(self, tf_value: bool) -> None:
        """Push a new IF level onto the stack with the given boolean value."""
        self.if_levels.append(IfItem(tf_value))

    def unnest(self) -> None:
        """Pop the innermost IF level; raise ErrInfo if the stack is empty."""
        if len(self.if_levels) == 0:
            raise ErrInfo(type="error", other_msg="Can't exit an IF block; no IF block is active.")
        else:
            self.if_levels.pop()

    def invert(self) -> None:
        if len(self.if_levels) == 0:
            raise ErrInfo(type="error", other_msg="Can't change the IF state; no IF block is active.")
        else:
            self.if_levels[-1].invert()

    def replace(self, tf_value: bool) -> None:
        if len(self.if_levels) == 0:
            raise ErrInfo(type="error", other_msg="Can't change the IF state; no IF block is active.")
        else:
            self.if_levels[-1].change_to(tf_value)

    def current(self) -> bool:
        if len(self.if_levels) == 0:
            raise ErrInfo(type="error", other_msg="No IF block is active.")
        else:
            return self.if_levels[-1].value()

    def all_true(self) -> bool:
        """Return True if every active IF level is true (or the stack is empty)."""
        if self.if_levels == []:
            return True
        return all(tf.value() for tf in self.if_levels)

    def only_current_false(self) -> bool:
        # Returns True if the current if level is false and all higher levels are True.
        if len(self.if_levels) == 0:
            return False
        elif len(self.if_levels) == 1:
            return not self.if_levels[-1].value()
        else:
            return not self.if_levels[-1].value() and all(tf.value() for tf in self.if_levels[:-1])

    def script_lines(self, top_n: int) -> list[tuple]:
        # Returns a list of tuples containing the script name and line number
        # for the topmost 'top_n' if levels, in bottom-up order.
        if len(self.if_levels) < top_n:
            raise ErrInfo(type="error", other_msg="Invalid IF stack depth reference.")
        levels = self.if_levels[len(self.if_levels) - top_n :]
        return [lvl.script_line() for lvl in levels]
