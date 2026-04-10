"""Abstract base class for execsql GUI backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

__all__ = ["DiffResult", "GuiBackend", "compare_stats", "compute_row_diffs"]

DIFF_MARKER = "● "


# ---------------------------------------------------------------------------
# Value comparison helpers
# ---------------------------------------------------------------------------


def _values_equal(a: Any, b: Any) -> bool:
    """Compare two cell values using native equality.

    Rules:
    - ``None == None`` → True
    - ``None`` vs any non-None → False  (NULL is distinct from empty string)
    - Numeric types are compared numerically (``int(1) == float(1.0)``,
      ``Decimal("10.00") == Decimal("10.0")``)
    - All other types use ``==``
    - Falls back to ``repr()`` comparison for exotic types that raise on ``==``
    """
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        return bool(a == b)
    except (TypeError, ValueError):
        return repr(a) == repr(b)


def _pk_tuple(row: list | tuple, pk_indices: list[int]) -> tuple:
    """Extract a PK value tuple from *row*.

    PK values are stringified so that type differences in key columns
    (e.g. ``int(1)`` vs ``str("1")``) still match rows correctly.
    ``None`` is preserved as-is so distinct NULL-keyed rows are not
    collapsed (in practice PK columns are NOT NULL).
    """
    return tuple(str(row[i]) if row[i] is not None else None for i in pk_indices)


# ---------------------------------------------------------------------------
# DiffResult and compute_row_diffs
# ---------------------------------------------------------------------------


@dataclass
class DiffResult:
    """Per-row diff state for compare dialogs.

    Attributes:
        table1_row_states: ``"match"`` / ``"changed"`` / ``"only_t1"`` per row.
        table2_row_states: Same for table 2.
        table1_changed_cols: For each table-1 row, set of column names that differ.
        table2_changed_cols: Same for table 2.
        summary: Human-readable summary string.
    """

    table1_row_states: list[str] = field(default_factory=list)
    table2_row_states: list[str] = field(default_factory=list)
    table1_changed_cols: list[set[str]] = field(default_factory=list)
    table2_changed_cols: list[set[str]] = field(default_factory=list)
    summary: str = ""


def compute_row_diffs(
    headers1: list,
    rows1: list,
    headers2: list,
    rows2: list,
    keylist: list,
) -> DiffResult | None:
    """Compare two tables row-by-row and return per-cell diff information.

    Rows are matched by the key columns in *keylist*, not by position.
    Columns are matched by header name, not index — headers may differ in
    order or membership.  Only columns present in **both** headers (minus
    key columns) are compared for cell-level diffs.

    Values are compared with native Python equality via :func:`_values_equal`:
    numeric types compare numerically, ``None`` is distinct from ``""``,
    and exotic types fall back to ``repr()``.

    When duplicate PK values exist in a table, the **first** row with that
    key is kept and later duplicates are ignored.

    Returns ``None`` when *keylist* is empty or a key column is missing
    from either header.
    """
    if not keylist:
        return None
    headers1_str = [str(h) for h in headers1]
    headers2_str = [str(h) for h in headers2]
    key_idx1 = [i for i, h in enumerate(headers1_str) if h in keylist]
    key_idx2 = [i for i, h in enumerate(headers2_str) if h in keylist]
    if not key_idx1 or not key_idx2:
        return None

    # Build PK -> row-index maps (first occurrence wins for duplicates).
    pk_map1: dict[tuple, int] = {}
    for i, r in enumerate(rows1):
        k = _pk_tuple(r, key_idx1)
        if k not in pk_map1:
            pk_map1[k] = i
    pk_map2: dict[tuple, int] = {}
    for i, r in enumerate(rows2):
        k = _pk_tuple(r, key_idx2)
        if k not in pk_map2:
            pk_map2[k] = i

    keys1 = set(pk_map1)
    keys2 = set(pk_map2)
    common = keys1 & keys2

    # Shared non-key columns eligible for cell comparison.
    key_set = set(keylist)
    h1_idx = {h: i for i, h in enumerate(headers1_str)}
    h2_idx = {h: i for i, h in enumerate(headers2_str)}
    shared_cols = [h for h in headers1_str if h in h2_idx and h not in key_set]

    # Initialise result lists.
    t1_states: list[str] = [""] * len(rows1)
    t2_states: list[str] = [""] * len(rows2)
    t1_changed: list[set[str]] = [set() for _ in rows1]
    t2_changed: list[set[str]] = [set() for _ in rows2]

    for k in keys1 - keys2:
        t1_states[pk_map1[k]] = "only_t1"
    for k in keys2 - keys1:
        t2_states[pk_map2[k]] = "only_t2"

    matching = 0
    differing = 0
    for k in common:
        i1 = pk_map1[k]
        i2 = pk_map2[k]
        changed: set[str] = set()
        for col in shared_cols:
            if not _values_equal(rows1[i1][h1_idx[col]], rows2[i2][h2_idx[col]]):
                changed.add(col)
        if changed:
            t1_states[i1] = "changed"
            t2_states[i2] = "changed"
            t1_changed[i1] = changed
            t2_changed[i2] = set(changed)
            differing += 1
        else:
            t1_states[i1] = "match"
            t2_states[i2] = "match"
            matching += 1

    only1 = len(keys1 - keys2)
    only2 = len(keys2 - keys1)
    parts: list[str] = []
    if matching:
        parts.append(f"{matching:,} matching")
    if differing:
        parts.append(f"{differing:,} differing")
    if only1:
        parts.append(f"{only1:,} only in Table 1")
    if only2:
        parts.append(f"{only2:,} only in Table 2")
    summary = " | ".join(parts) if parts else "Tables are identical"

    return DiffResult(
        table1_row_states=t1_states,
        table2_row_states=t2_states,
        table1_changed_cols=t1_changed,
        table2_changed_cols=t2_changed,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# compare_stats — delegates to compute_row_diffs for consistency
# ---------------------------------------------------------------------------


def compare_stats(
    headers1: list,
    rows1: list,
    headers2: list,
    rows2: list,
    keylist: list,
) -> str:
    """Return a one-line diff summary for compare dialogs.

    Delegates to :func:`compute_row_diffs` so that the summary and the
    cell-level diff always agree.  Returns an empty string when *keylist*
    is empty or key columns are missing.
    """
    result = compute_row_diffs(headers1, rows1, headers2, rows2, keylist)
    if result is None:
        return ""
    return result.summary


class GuiBackend(ABC):
    """Abstract base for all GUI backends.

    Each backend implements one method per GuiSpec type.
    ``dispatch()`` routes GuiSpec requests to the appropriate handler.

    Return value conventions:
    - ``show_halt``       → ``{"button": 1}``
    - ``show_msg``        → ``{"button": 1}``
    - ``show_pause``      → ``{"quit": bool}``
    - ``show_display``    → ``{"button": int|None, "return_value": str|None}``
    - ``show_entry_form`` → ``{"button": int|None, "return_value": list[EntrySpec]}``
    - ``show_compare``    → ``{"button": int|None}``
    - ``show_select_rows``→ ``{"button": int|None}``
    - ``show_select_sub`` → ``{"button": int|None, "row": dict|None}``
    - ``show_action``     → ``{"button": int|None}``
    - ``show_map``        → ``{"button": int|None}``
    - ``show_open_file``  → ``{"filename": str|None}``
    - ``show_save_file``  → ``{"filename": str|None}``
    - ``show_directory``  → ``{"directory": str|None}``
    - ``query_console``   → ``{"console_running": bool}``
    - ``show_credentials``→ ``{"username": str, "password": str}``
    - ``show_connect``    → ``{"db_type": str, "server": str, ...}``
    """

    def dispatch(self, spec: Any) -> dict:
        """Dispatch a GuiSpec to the appropriate handler method."""
        from execsql.utils.gui import (
            GUI_ACTION,
            GUI_COMPARE,
            GUI_CONNECT,
            GUI_CREDENTIALS,
            GUI_DIRECTORY,
            GUI_DISPLAY,
            GUI_ENTRY,
            GUI_HALT,
            GUI_MAP,
            GUI_MSG,
            GUI_OPENFILE,
            GUI_PAUSE,
            GUI_SAVEFILE,
            GUI_SELECTROWS,
            GUI_SELECTSUB,
            QUERY_CONSOLE,
        )

        handlers = {
            GUI_HALT: self.show_halt,
            GUI_MSG: self.show_msg,
            GUI_PAUSE: self.show_pause,
            GUI_DISPLAY: self.show_display,
            GUI_ENTRY: self.show_entry_form,
            GUI_COMPARE: self.show_compare,
            GUI_SELECTROWS: self.show_select_rows,
            GUI_SELECTSUB: self.show_select_sub,
            GUI_ACTION: self.show_action,
            GUI_MAP: self.show_map,
            GUI_OPENFILE: self.show_open_file,
            GUI_SAVEFILE: self.show_save_file,
            GUI_DIRECTORY: self.show_directory,
            QUERY_CONSOLE: self.query_console,
            GUI_CREDENTIALS: self.show_credentials,
            GUI_CONNECT: self.show_connect,
        }
        handler = handlers.get(spec.gui_type)
        if handler is None:
            return {"error": f"Unknown GUI type: {spec.gui_type}", "button": None}
        return handler(spec.args)

    def start(self) -> None:
        """Called when the backend is started. Override for setup."""

    def stop(self) -> None:
        """Called when the backend is stopped. Override for teardown."""

    def console_on(self) -> None:
        """Start the console window (if applicable)."""

    def console_off(self) -> None:
        """Stop the console window (if applicable)."""

    def console_hide(self) -> None:
        """Hide the console window (if applicable)."""

    def console_show(self) -> None:
        """Show the console window (if applicable)."""

    def console_progress(self, num: float, total: float | None = None) -> None:
        """Update the progress indicator."""

    def console_save(self, outfile: str, append: bool = False) -> None:
        """Save console contents to a file."""

    def console_status(self, message: str) -> None:
        """Set the status bar message."""

    def console_wait_user(self, message: str = "") -> None:
        """Block until the user dismisses the console."""

    # ------------------------------------------------------------------
    # Abstract dialog methods — must be implemented by each backend.
    # ------------------------------------------------------------------

    @abstractmethod
    def show_halt(self, args: dict) -> dict:
        """Show a HALT message dialog."""

    @abstractmethod
    def show_msg(self, args: dict) -> dict:
        """Show a message dialog."""

    @abstractmethod
    def show_pause(self, args: dict) -> dict:
        """Show a pause dialog with optional countdown."""

    @abstractmethod
    def show_display(self, args: dict) -> dict:
        """Show a data display / query result dialog."""

    @abstractmethod
    def show_entry_form(self, args: dict) -> dict:
        """Show a multi-field entry form."""

    @abstractmethod
    def show_compare(self, args: dict) -> dict:
        """Show a table comparison dialog."""

    @abstractmethod
    def show_select_rows(self, args: dict) -> dict:
        """Show a row selection dialog."""

    @abstractmethod
    def show_select_sub(self, args: dict) -> dict:
        """Show a single-row selection dialog."""

    @abstractmethod
    def show_action(self, args: dict) -> dict:
        """Show an action button grid dialog."""

    @abstractmethod
    def show_map(self, args: dict) -> dict:
        """Show a map display dialog."""

    @abstractmethod
    def show_open_file(self, args: dict) -> dict:
        """Show a file open dialog."""

    @abstractmethod
    def show_save_file(self, args: dict) -> dict:
        """Show a file save dialog."""

    @abstractmethod
    def show_directory(self, args: dict) -> dict:
        """Show a directory selection dialog."""

    @abstractmethod
    def query_console(self, args: dict) -> dict:
        """Return whether the GUI console is currently running."""

    @abstractmethod
    def show_credentials(self, args: dict) -> dict:
        """Show a credentials (username + password) dialog."""

    @abstractmethod
    def show_connect(self, args: dict) -> dict:
        """Show a database connection selection dialog."""
