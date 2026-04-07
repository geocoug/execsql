"""Textual TUI backend for execsql.

Each dialog type is implemented as a standalone Textual ModalScreen that is
pushed onto the ConductorApp's screen stack from the main thread.

Architecture
------------
Textual requires its event loop (and therefore signal handlers) to run in the
main thread.  To satisfy this constraint, when gui_level >= 1 execsql runs the
SQL script in a background thread and keeps the main thread for the Textual
``ConductorApp``.  Metacommand code puts ``GuiSpec`` objects onto
``_state.gui_manager_queue``; the conductor polls that queue and serves each
request by pushing the appropriate ``ModalScreen`` via ``push_screen_wait()``.

Install with: pip install "execsql2[tui]"
"""

from __future__ import annotations

import ctypes
import os
import queue as _stdlib_queue
import threading
from typing import Any

from execsql.gui.base import GuiBackend

# ---------------------------------------------------------------------------
# Textual import guard — raises ImportError if not installed so that the
# factory in gui/__init__.py can fall back gracefully.
# ---------------------------------------------------------------------------
try:
    import textual  # noqa: F401
except ImportError as _e:
    raise ImportError(
        "Textual is not installed. Install it with: pip install 'execsql2[tui]'",
    ) from _e

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    DirectoryTree,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RadioButton,
    RadioSet,
    RichLog,
    Select,
    SelectionList,
    Static,
)

__all__ = ["TextualBackend"]

from execsql.gui.base import compare_stats as _compare_stats

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_count_text(n: int) -> str:
    """Return a human-readable row count string, e.g. '3 rows' or '1 row'."""
    return f"{n:,} row{'s' if n != 1 else ''}"


def _make_table_widget(table_id: str, headers: list, rows: list) -> DataTable:
    """Build a DataTable widget populated with data."""
    dt: DataTable = DataTable(id=table_id, zebra_stripes=True, cursor_type="row")
    dt.add_columns(*[str(h) for h in headers])
    for row in rows:
        dt.add_row(*[str(c) if c is not None else "" for c in row])
    return dt


def _help_button(url: str | None) -> Button | None:
    """Return a Help button if *url* is truthy, otherwise None."""
    if url:
        return Button("Help", id="btn_help", variant="default")
    return None


def _button_row(button_list: list) -> list[Button]:
    """Create Button widgets from a button_list of (label, value, key?) tuples.

    A Cancel button (id ``btn_cancel_exit``) is always prepended so it appears
    on the left while the primary action button sits on the far right.
    Entries in *button_list* with a falsy value (0 or None) are treated as the
    cancel label source and are otherwise excluded from the numbered buttons so
    that ``btn_N`` indices stay aligned with ``button_list`` positions.
    """
    cancel_label = "Cancel"
    primary_buttons = []
    for i, btn in enumerate(button_list):
        label, value = btn[0], btn[1]
        if not value and value != 1:  # falsy but not accidentally 1
            cancel_label = label
        else:
            variant = "primary" if i == 0 else "default"
            primary_buttons.append(Button(label, id=f"btn_{i}", variant=variant))
    return [Button(cancel_label, id="btn_cancel_exit", variant="warning")] + primary_buttons


# ---------------------------------------------------------------------------
# Base dialog mix-in (ModalScreen)
# ---------------------------------------------------------------------------


class _BaseDialog(ModalScreen):
    """Common infrastructure for all execsql dialog screens."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    _BaseDialog {
        align: center middle;
    }
    #dialog {
        background: $surface;
        border: round $primary;
        padding: 1 2;
        min-width: 60;
        max-width: 120;
        min-height: 8;
        height: auto;
        max-height: 95%;
        overflow-y: auto;
    }
    #title {
        text-style: bold;
        margin-bottom: 1;
    }
    #message {
        margin-bottom: 1;
    }
    #buttons {
        dock: bottom;
        height: 3;
        align: right middle;
        margin-top: 1;
        background: $surface;
    }
    Button {
        margin: 0 1;
    }
    DataTable {
        max-height: 15;
        margin-bottom: 0;
    }
    .row-count {
        color: $text-muted;
        margin-bottom: 1;
    }
    Input {
        margin-bottom: 1;
    }
    #btn_help {
        dock: right;
        margin: 0 0 1 1;
        min-width: 8;
    }
    """

    def __init__(self, args: dict) -> None:
        super().__init__()
        self.args = args
        self._result: dict = {}

    @property
    def result(self) -> dict:
        return self._result

    def action_cancel(self) -> None:
        """Dismiss the dialog as cancelled (triggered by Escape key)."""
        self._result = {"button": None, "cancelled": True}
        self.dismiss(self._result)

    @on(Button.Pressed, "#btn_cancel_exit")
    def _on_cancel_exit(self, event: Button.Pressed) -> None:
        """Universal Cancel handler — dismisses with cancelled=True so the sync queue can exit."""
        event.stop()
        self._result = {"button": None, "cancelled": True}
        self.dismiss(self._result)

    @on(Button.Pressed, "#btn_help")
    def _on_help(self, event: Button.Pressed) -> None:
        """Open the help URL in the system browser without dismissing the dialog."""
        event.stop()
        import webbrowser

        url = self.args.get("help_url", "")
        if url:
            webbrowser.open(url)


# ---------------------------------------------------------------------------
# MSG dialog
# ---------------------------------------------------------------------------


class MsgScreen(_BaseDialog):
    """Simple message dialog with Continue and Cancel buttons."""

    BINDINGS = [
        *_BaseDialog.BINDINGS,
        Binding("enter", "submit", "Continue", show=True),
    ]

    def compose(self) -> ComposeResult:
        title = self.args.get("title", "Message")
        message = self.args.get("message", "")
        with Container(id="dialog"):
            yield Label(title, id="title")
            yield Static(message, id="message")
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="btn_cancel_exit", variant="warning")
                yield Button("Continue", id="btn_close", variant="primary")

    def action_submit(self) -> None:
        """Continue the dialog (triggered by Enter key)."""
        self._result = {"button": 1}
        self.dismiss(self._result)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_close":
            self._result = {"button": 1}
            self.dismiss(self._result)


# ---------------------------------------------------------------------------
# PAUSE dialog
# ---------------------------------------------------------------------------


class PauseScreen(_BaseDialog):
    """Pause dialog with optional countdown and Continue/Cancel buttons."""

    BINDINGS = [
        *_BaseDialog.BINDINGS,
        Binding("enter", "submit", "Continue", show=True),
    ]

    def compose(self) -> ComposeResult:
        title = self.args.get("title", "Pause")
        message = self.args.get("message", "")
        with Container(id="dialog"):
            yield Label(title, id="title")
            yield Static(message, id="message")
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="btn_cancel_exit", variant="warning")
                yield Button("Continue", id="btn_continue", variant="primary")

    def on_mount(self) -> None:
        countdown = self.args.get("countdown")
        if countdown is not None:
            self.set_timer(float(countdown), self._auto_continue)

    def _auto_continue(self) -> None:
        self._result = {"quit": False}
        self.dismiss(self._result)

    def action_submit(self) -> None:
        """Continue the dialog (triggered by Enter key)."""
        self._result = {"quit": False}
        self.dismiss(self._result)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_continue":
            self._result = {"quit": False}
            self.dismiss(self._result)


# ---------------------------------------------------------------------------
# DISPLAY dialog (table + optional entry + buttons)
# ---------------------------------------------------------------------------


class DisplayScreen(_BaseDialog):
    """Data display dialog: title, message, optional table, optional text entry, buttons."""

    BINDINGS = [
        *_BaseDialog.BINDINGS,
        Binding("enter", "submit", "Submit", show=True),
    ]

    def compose(self) -> ComposeResult:
        title = self.args.get("title", "")
        message = self.args.get("message", "")
        headers = self.args.get("column_headers") or []
        rows = self.args.get("rowset") or []
        button_list = self.args.get("button_list", [("Continue", 1)])
        textentry = self.args.get("textentry", False)
        hidetext = self.args.get("hidetext", False)
        initial = self.args.get("initialtext", "")

        with Container(id="dialog"):
            if title:
                yield Label(title, id="title")
            help_btn = _help_button(self.args.get("help_url"))
            if help_btn:
                yield help_btn
            if message:
                yield Static(message, id="message")
            if headers and rows:
                with ScrollableContainer(id="table_container"):
                    yield _make_table_widget("main_table", headers, rows)
                yield Static(_row_count_text(len(rows)), classes="row-count")
            if textentry:
                yield Input(
                    value=initial,
                    password=hidetext,
                    placeholder="Enter a value",
                    id="text_input",
                )
            with Horizontal(id="buttons"):
                yield from _button_row(button_list)

    def action_submit(self) -> None:
        """Submit the first primary button value (triggered by Enter key)."""
        button_list = self.args.get("button_list", [("Continue", 1)])
        # Find the first non-cancel button value.
        value = None
        for btn in button_list:
            if btn[1]:
                value = btn[1]
                break
        if value is None:
            return
        text_input = self.query_one("#text_input", Input) if self.args.get("textentry") else None
        return_value = text_input.value if text_input else None
        self._result = {"button": value, "return_value": return_value}
        self.dismiss(self._result)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id and btn_id.startswith("btn_") and btn_id[4:].isdigit():
            idx = int(btn_id.split("_")[1])
            button_list = self.args.get("button_list", [("Continue", 1)])
            value = button_list[idx][1]
            text_input = self.query_one("#text_input", Input) if self.args.get("textentry") else None
            return_value = text_input.value if text_input else None
            self._result = {"button": value, "return_value": return_value}
            self.dismiss(self._result)


# ---------------------------------------------------------------------------
# ENTRY_FORM dialog
# ---------------------------------------------------------------------------


class EntryFormScreen(_BaseDialog):
    """Multi-field entry form dialog."""

    BINDINGS = [
        *_BaseDialog.BINDINGS,
        Binding("enter", "submit", "OK", show=True),
    ]

    DEFAULT_CSS = (
        _BaseDialog.DEFAULT_CSS
        + """
    .field-row {
        height: auto;
        min-height: 3;
        margin-bottom: 1;
    }
    .field-label {
        width: 25;
        content-align: right middle;
        padding-right: 1;
    }
    .field-input {
        width: 1fr;
    }
    """
    )

    def __init__(self, args: dict) -> None:
        super().__init__(args)
        self._inputs: dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        title = self.args.get("title", "Entry")
        message = self.args.get("message", "")
        specs = self.args.get("entry_specs", [])
        headers = self.args.get("column_headers") or []
        rows = self.args.get("rowset") or []

        with Container(id="dialog"):
            if title:
                yield Label(title, id="title")
            help_btn = _help_button(self.args.get("help_url"))
            if help_btn:
                yield help_btn
            if message:
                yield Static(message, id="message")
            if headers and rows:
                with ScrollableContainer():
                    yield _make_table_widget("form_table", headers, rows)
                yield Static(_row_count_text(len(rows)), classes="row-count")
            with ScrollableContainer(id="fields"):
                for spec in specs:
                    etype = (spec.entry_type or "text").lower()
                    field_id = f"field_{spec.varname}"
                    # Compute the display label (radiobuttons uses semicolon-delimited)
                    if etype == "radiobuttons":
                        parts = (spec.label or "").split(";")
                        field_label = parts[0].strip() if parts else (spec.varname or "")
                    else:
                        field_label = spec.label or spec.varname or ""

                    if etype == "listbox" and spec.lookup_list:
                        # Multi-row widget — render label + SelectionList vertically
                        yield Static(field_label, classes="row-count")
                        height = spec.default_height or 4
                        sl = SelectionList[str](
                            *[(str(v), str(v), False) for v in spec.lookup_list if v is not None],
                            id=field_id,
                        )
                        sl.styles.height = height + 2
                        yield sl
                        self._inputs[spec.varname] = sl
                    elif etype == "radiobuttons":
                        # Multi-row widget — render label + RadioSet vertically
                        yield Static(field_label, classes="row-count")
                        buttons = parts[1:] if len(parts) > 1 else ["Option"]
                        rs = RadioSet(
                            *[RadioButton(str(b).strip()) for b in buttons if b is not None],
                            id=field_id,
                        )
                        yield rs
                        self._inputs[spec.varname] = rs
                    else:
                        # Single-row widgets — render in a Horizontal row
                        with Horizontal(classes="field-row"):
                            yield Label(field_label, classes="field-label")
                            if etype == "checkbox":
                                initial = (spec.initial_value or "").lower() in ("true", "1", "yes")
                                cb = Checkbox(label="", value=initial, id=field_id)
                                yield cb
                                self._inputs[spec.varname] = cb
                            elif etype in ("dropdown", "select") and spec.lookup_list:
                                # Input with placeholder (Select overlay crashes in modal dialogs)
                                valid = ", ".join(str(v) for v in spec.lookup_list if v is not None)
                                inp = Input(
                                    value=spec.initial_value or str(spec.lookup_list[0] or ""),
                                    id=field_id,
                                    classes="field-input",
                                    placeholder=f"Choose: {valid}",
                                )
                                yield inp
                                self._inputs[spec.varname] = inp
                            elif etype == "textarea":
                                inp = Input(
                                    value=str(spec.initial_value) if spec.initial_value else "",
                                    id=field_id,
                                    classes="field-input",
                                    placeholder="Enter text",
                                )
                                yield inp
                                self._inputs[spec.varname] = inp
                            elif etype in ("inputfile", "outputfile"):
                                inp = Input(
                                    value=str(spec.initial_value) if spec.initial_value else "",
                                    id=field_id,
                                    classes="field-input",
                                    placeholder="Enter file path or click Browse",
                                )
                                yield inp
                                yield Button(
                                    "Browse…",
                                    id=f"browse_{spec.varname}",
                                    variant="default",
                                )
                                self._inputs[spec.varname] = inp
                            else:
                                inp = Input(
                                    value=str(spec.initial_value) if spec.initial_value else "",
                                    id=field_id,
                                    classes="field-input",
                                    restrict=spec.validation_key_regex or None,
                                )
                                yield inp
                                self._inputs[spec.varname] = inp
            # File browser panel (hidden by default, shown when Browse is clicked)
            dt = DirectoryTree(".", id="file_tree")
            dt.styles.height = 10
            dt.styles.display = "none"
            yield dt
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="btn_cancel_exit", variant="warning")
                yield Button("OK", id="btn_ok", variant="primary")

        self._specs = specs
        self._browse_target: str | None = None

    def _on_browse_pressed(self, event: Button.Pressed) -> None:
        """Show/hide the file browser when a Browse button is clicked."""
        btn_id = event.button.id or ""
        if not btn_id.startswith("browse_"):
            return
        event.stop()
        varname = btn_id[len("browse_") :]
        tree = self.query_one("#file_tree", DirectoryTree)
        if tree.styles.display == "none":
            self._browse_target = varname
            tree.styles.display = "block"
            tree.focus()
        else:
            tree.styles.display = "none"
            self._browse_target = None

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Populate the target Input with the selected file path."""
        if self._browse_target and self._browse_target in self._inputs:
            widget = self._inputs[self._browse_target]
            widget.value = str(event.path)
        tree = self.query_one("#file_tree", DirectoryTree)
        tree.styles.display = "none"
        self._browse_target = None

    def _collect_values(self) -> None:
        """Read widget values into the EntrySpec objects."""
        for spec in self._specs:
            widget = self._inputs.get(spec.varname)
            if widget is None:
                continue
            etype = (spec.entry_type or "text").lower()
            if etype == "checkbox":
                spec.value = "1" if widget.value else "0"
            elif etype == "listbox" and isinstance(widget, SelectionList):
                selected = widget.selected
                items = [str(widget.get_option_at_index(i).value) for i in selected]
                spec.value = ",".join(f"'{v.replace(chr(39), chr(39) + chr(39))}'" for v in items)
            elif etype == "radiobuttons" and isinstance(widget, RadioSet):
                spec.value = str(widget.pressed_index + 1) if widget.pressed_index >= 0 else "1"
            else:
                spec.value = widget.value

    def _validate(self) -> list[str]:
        """Validate collected values. Returns list of error messages (empty = valid)."""
        import re as _re

        errors: list[str] = []
        for spec in self._specs:
            val = spec.value or ""
            etype = (spec.entry_type or "text").lower()
            if spec.required and not val and etype != "checkbox":
                errors.append(f"{spec.label or spec.varname}: required")
            if spec.validation_regex and val and not _re.fullmatch(spec.validation_regex, val):
                errors.append(f"{spec.label or spec.varname}: does not match pattern")
        return errors

    def _submit_form(self) -> None:
        """Collect, validate, and dismiss if valid."""
        self._collect_values()
        errors = self._validate()
        if errors:
            self.notify("\n".join(errors), title="Validation Error", severity="error")
            return
        self._result = {"button": 1, "return_value": self._specs}
        self.dismiss(self._result)

    def action_submit(self) -> None:
        """Submit the form (triggered by Enter key)."""
        self._submit_form()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id.startswith("browse_"):
            self._on_browse_pressed(event)
            return
        if btn_id == "btn_ok":
            self._submit_form()


# ---------------------------------------------------------------------------
# COMPARE dialog
# ---------------------------------------------------------------------------


class CompareScreen(_BaseDialog):
    """Side-by-side table comparison dialog."""

    BINDINGS = [
        *_BaseDialog.BINDINGS,
        Binding("enter", "submit", "Continue", show=True),
    ]

    DEFAULT_CSS = (
        _BaseDialog.DEFAULT_CSS
        + """
    #tables_scroll {
        height: 1fr;
        min-height: 8;
    }
    #tables {
        height: auto;
    }
    .compare-table {
        width: 1fr;
        height: auto;
        margin: 0 1;
    }
    .compare-table DataTable {
        height: auto;
        max-height: 10;
    }
    #diff_toolbar {
        height: auto;
        margin-bottom: 1;
    }
    #diff_legend {
        color: $text-muted;
        margin-bottom: 1;
    }
    """
    )

    def __init__(self, args: dict) -> None:
        super().__init__(args)
        self._syncing = False
        self._key_idx1: list = []
        self._key_idx2: list = []
        self._kv_to_ridx1: dict = {}
        self._kv_to_ridx2: dict = {}
        self._col_keys1: list = []
        self._col_keys2: list = []
        self._diff_on = False
        self._original_cells1: dict = {}
        self._original_cells2: dict = {}

    def compose(self) -> ComposeResult:
        title = self.args.get("title", "Compare")
        message = self.args.get("message", "")
        headers1 = self.args.get("headers1", [])
        rows1 = self.args.get("rows1", [])
        headers2 = self.args.get("headers2", [])
        rows2 = self.args.get("rows2", [])
        button_list = self.args.get("button_list", [("Continue", 1)])
        sidebyside = self.args.get("sidebyside", True)
        tables_container = Horizontal if sidebyside else Vertical

        with Container(id="dialog"):
            if title:
                yield Label(title, id="title")
            help_btn = _help_button(self.args.get("help_url"))
            if help_btn:
                yield help_btn
            if message:
                yield Static(message, id="message")
            if self.args.get("keylist"):
                with Horizontal(id="diff_toolbar"):
                    yield Button("Highlight Diffs", id="btn_diff_toggle", variant="default")
                    yield Static(
                        "  [on #2d5a2d] Match [/]  [on #5a4b00] Changed [/]  [on #5a1a1a] Only in one [/]",
                        id="diff_legend",
                    )
            with ScrollableContainer(id="tables_scroll"), tables_container(id="tables"):
                with Vertical(classes="compare-table"):
                    yield Label("Table 1")
                    yield _make_table_widget("table1", headers1, rows1)
                    yield Static(_row_count_text(len(rows1)), classes="row-count")
                with Vertical(classes="compare-table"):
                    yield Label("Table 2")
                    yield _make_table_widget("table2", headers2, rows2)
                    yield Static(_row_count_text(len(rows2)), classes="row-count")
            summary = _compare_stats(
                headers1,
                rows1,
                headers2,
                rows2,
                [str(k) for k in self.args.get("keylist", [])],
            )
            if summary:
                yield Static(summary, classes="row-count")
            with Horizontal(id="buttons"):
                yield from _button_row(button_list)

    def on_mount(self) -> None:
        keylist = [str(k) for k in self.args.get("keylist", [])]
        if not keylist:
            return
        headers1 = [str(h) for h in self.args.get("headers1", [])]
        headers2 = [str(h) for h in self.args.get("headers2", [])]
        rows1 = self.args.get("rows1", [])
        rows2 = self.args.get("rows2", [])

        self._key_idx1 = [i for i, h in enumerate(headers1) if h in keylist]
        self._key_idx2 = [i for i, h in enumerate(headers2) if h in keylist]

        def _kv(row: list, idxs: list) -> tuple:
            return tuple(str(row[i]) if row[i] is not None else "" for i in idxs)

        self._kv_to_ridx1 = {_kv(r, self._key_idx1): i for i, r in enumerate(rows1)}
        self._kv_to_ridx2 = {_kv(r, self._key_idx2): i for i, r in enumerate(rows2)}

        t1: DataTable = self.query_one("#table1", DataTable)
        t2: DataTable = self.query_one("#table2", DataTable)
        self._col_keys1 = list(t1.columns.keys())
        self._col_keys2 = list(t2.columns.keys())

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if self._syncing or not self._key_idx1:
            return
        src_id = event.data_table.id
        if src_id == "table1":
            col_keys, key_idx, kv_map, other_id = self._col_keys1, self._key_idx1, self._kv_to_ridx2, "table2"
        elif src_id == "table2":
            col_keys, key_idx, kv_map, other_id = self._col_keys2, self._key_idx2, self._kv_to_ridx1, "table1"
        else:
            return
        if not key_idx or not kv_map:
            return
        row_key = event.row_key
        src: DataTable = event.data_table
        kv = tuple(str(src.get_cell(row_key, col_keys[i])) for i in key_idx)
        match_ridx = kv_map.get(kv)
        if match_ridx is None:
            return
        other: DataTable = self.query_one(f"#{other_id}", DataTable)
        self._syncing = True
        try:
            other.move_cursor(row=match_ridx, animate=False)
        finally:
            self._syncing = False

    @on(Button.Pressed, "#btn_diff_toggle")
    def _on_diff_toggle(self, event: Button.Pressed) -> None:
        """Toggle row-level diff highlighting in both tables."""
        event.stop()
        from rich.text import Text

        self._diff_on = not self._diff_on
        t1: DataTable = self.query_one("#table1", DataTable)
        t2: DataTable = self.query_one("#table2", DataTable)
        rows1 = self.args.get("rows1", [])
        rows2 = self.args.get("rows2", [])
        row_keys1 = list(t1.rows.keys())
        row_keys2 = list(t2.rows.keys())

        if not self._diff_on:
            # Restore original cell values
            for (rk, ck), val in self._original_cells1.items():
                t1.update_cell(rk, ck, val)
            for (rk, ck), val in self._original_cells2.items():
                t2.update_cell(rk, ck, val)
            self._original_cells1.clear()
            self._original_cells2.clear()
            return

        keys1_set = set(self._kv_to_ridx1.keys())
        keys2_set = set(self._kv_to_ridx2.keys())
        ridx_to_kv1 = {v: k for k, v in self._kv_to_ridx1.items()}
        ridx_to_kv2 = {v: k for k, v in self._kv_to_ridx2.items()}
        row_map1 = {k: rows1[i] for k, i in self._kv_to_ridx1.items()}
        row_map2 = {k: rows2[i] for k, i in self._kv_to_ridx2.items()}

        # Muted colors suitable for dark terminal themes
        style_match = "on #2d5a2d"
        style_changed = "on #5a4b00"
        style_only = "on #5a1a1a"

        def _style_table(
            table: DataTable,
            originals: dict,
            row_keys: list,
            col_keys: list,
            data_rows: list,
            ridx_to_kv: dict,
            other_keys_set: set,
            other_row_map: dict,
        ) -> None:
            for ridx in range(len(data_rows)):
                kv = ridx_to_kv.get(ridx)
                if kv is None:
                    continue
                rk = row_keys[ridx]
                if kv not in other_keys_set:
                    style = style_only
                else:
                    r_self = [str(v) if v is not None else "" for v in data_rows[ridx]]
                    r_other = [str(v) if v is not None else "" for v in other_row_map[kv]]
                    style = style_match if r_self == r_other else style_changed
                for ck in col_keys:
                    val = table.get_cell(rk, ck)
                    originals[(rk, ck)] = val
                    table.update_cell(rk, ck, Text(str(val), style=style))

        _style_table(t1, self._original_cells1, row_keys1, self._col_keys1, rows1, ridx_to_kv1, keys2_set, row_map2)
        _style_table(t2, self._original_cells2, row_keys2, self._col_keys2, rows2, ridx_to_kv2, keys1_set, row_map1)

    def action_submit(self) -> None:
        """Submit the first primary button value (triggered by Enter key)."""
        button_list = self.args.get("button_list", [("Continue", 1)])
        for btn in button_list:
            if btn[1]:
                self._result = {"button": btn[1]}
                self.dismiss(self._result)
                return

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id and btn_id.startswith("btn_") and btn_id[4:].isdigit():
            idx = int(btn_id.split("_")[1])
            value = self.args.get("button_list", [("Continue", 1)])[idx][1]
            self._result = {"button": value}
            self.dismiss(self._result)


# ---------------------------------------------------------------------------
# SELECT_ROWS dialog
# ---------------------------------------------------------------------------


class SelectRowsScreen(_BaseDialog):
    """Row selection dialog: pick rows from source table and add to target."""

    BINDINGS = [
        *_BaseDialog.BINDINGS,
        Binding("enter", "submit", "Continue", show=True),
    ]

    DEFAULT_CSS = (
        _BaseDialog.DEFAULT_CSS
        + """
    #tables {
        height: 1fr;
        min-height: 10;
    }
    .sel-table {
        width: 1fr;
        margin: 0 1;
    }
    """
    )

    def compose(self) -> ComposeResult:
        title = self.args.get("title", "Select rows")
        message = self.args.get("message", "")
        headers1 = self.args.get("headers1", [])
        rows1 = self.args.get("rows1", [])
        headers2 = self.args.get("headers2", [])
        rows2 = self.args.get("rows2", [])
        button_list = self.args.get("button_list", [("Continue", 1)])

        with Container(id="dialog"):
            if title:
                yield Label(title, id="title")
            help_btn = _help_button(self.args.get("help_url"))
            if help_btn:
                yield help_btn
            if message:
                yield Static(message, id="message")
            yield Static("Double-click or press Enter on a row to add it to the right table.", id="hint")
            with Horizontal(id="tables"):
                with Vertical(classes="sel-table"):
                    yield Label("Source (select rows)")
                    yield _make_table_widget("source_table", headers1, rows1)
                    yield Static(_row_count_text(len(rows1)), classes="row-count")
                with Vertical(classes="sel-table"):
                    yield Label("Destination")
                    yield _make_table_widget("dest_table", headers2, rows2)
                    yield Static(_row_count_text(len(rows2)), classes="row-count")
            with Horizontal(id="buttons"):
                yield from _button_row(button_list)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "source_table":
            dest: DataTable = self.query_one("#dest_table", DataTable)
            row_key = event.row_key
            src: DataTable = self.query_one("#source_table", DataTable)
            values = [src.get_cell(row_key, col) for col in src.columns]
            dest.add_row(*values)

    def action_submit(self) -> None:
        """Submit the first primary button value (triggered by Enter key)."""
        button_list = self.args.get("button_list", [("Continue", 1)])
        for btn in button_list:
            if btn[1]:
                self._result = {"button": btn[1]}
                self.dismiss(self._result)
                return

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id and btn_id.startswith("btn_") and btn_id[4:].isdigit():
            idx = int(btn_id.split("_")[1])
            value = self.args.get("button_list", [("Continue", 1)])[idx][1]
            self._result = {"button": value}
            self.dismiss(self._result)


# ---------------------------------------------------------------------------
# SELECT_SUB dialog
# ---------------------------------------------------------------------------


class SelectSubScreen(_BaseDialog):
    """Single-row selection dialog: pick one row and assign column values to vars."""

    def __init__(self, args: dict) -> None:
        super().__init__(args)
        self._selected_row: dict | None = None
        self._headers: list = args.get("headers", [])

    def compose(self) -> ComposeResult:
        title = self.args.get("title", "Select a row")
        message = self.args.get("message", "")
        headers = self.args.get("headers", [])
        rows = self.args.get("rows", [])
        button_list = self.args.get("button_list", [("OK", 1), ("Cancel", 0)])

        with Container(id="dialog"):
            if title:
                yield Label(title, id="title")
            help_btn = _help_button(self.args.get("help_url"))
            if help_btn:
                yield help_btn
            if message:
                yield Static(message, id="message")
            yield Static("Click a row to select it.", id="hint")
            with ScrollableContainer():
                yield _make_table_widget("sel_table", headers, rows)
            yield Static(_row_count_text(len(rows)), classes="row-count")
            with Horizontal(id="buttons"):
                yield from _button_row(button_list)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        row_key = event.row_key
        tbl: DataTable = self.query_one("#sel_table", DataTable)
        values = [tbl.get_cell(row_key, col) for col in tbl.columns]
        self._selected_row = dict(zip(self._headers, values))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id and btn_id.startswith("btn_") and btn_id[4:].isdigit():
            idx = int(btn_id.split("_")[1])
            value = self.args.get("button_list", [("OK", 1), ("Cancel", 0)])[idx][1]
            self._result = {"button": value, "row": self._selected_row}
            self.dismiss(self._result)


# ---------------------------------------------------------------------------
# ACTION dialog
# ---------------------------------------------------------------------------


class ActionScreen(_BaseDialog):
    """Action button grid dialog."""

    BINDINGS = [
        *_BaseDialog.BINDINGS,
    ]

    def compose(self) -> ComposeResult:
        title = self.args.get("title", "Actions")
        message = self.args.get("message", "")
        button_specs = self.args.get("button_specs", [])
        headers = self.args.get("column_headers") or []
        rows = self.args.get("rowset") or []
        include_continue = self.args.get("include_continue_button")

        with Container(id="dialog"):
            if title:
                yield Label(title, id="title")
            help_btn = _help_button(self.args.get("help_url"))
            if help_btn:
                yield help_btn
            if message:
                yield Static(message, id="message")
            if headers and rows:
                with ScrollableContainer():
                    yield _make_table_widget("action_table", headers, rows)
                yield Static(_row_count_text(len(rows)), classes="row-count")
            with Vertical(id="action_buttons"):
                for i, spec in enumerate(button_specs):
                    yield Button(f"{spec.label} — {spec.prompt}", id=f"action_{i}", variant="primary")
                if include_continue:
                    yield Button("Continue", id="action_continue", variant="default")

        self._button_specs = button_specs

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "action_continue":
            self._result = {"button": 1}
        elif btn_id and btn_id.startswith("action_"):
            idx = int(btn_id.split("_")[1])
            self._result = {"button": idx + 1}
        self.dismiss(self._result)


# ---------------------------------------------------------------------------
# MAP dialog (tabular fallback — no interactive map in Textual)
# ---------------------------------------------------------------------------


class MapScreen(_BaseDialog):
    """Map display — shows coordinate data in a table (interactive map not available in TUI)."""

    def compose(self) -> ComposeResult:
        title = self.args.get("title", "Map")
        message = self.args.get("message", "")
        headers = self.args.get("headers", [])
        rows = self.args.get("rows", [])
        button_list = self.args.get("button_list", [("Continue", 1)])

        with Container(id="dialog"):
            if title:
                yield Label(title, id="title")
            if message:
                yield Static(message, id="message")
            yield Static("(Interactive map not available in TUI; showing tabular data)", id="note")
            if headers and rows:
                with ScrollableContainer():
                    yield _make_table_widget("map_table", headers, rows)
                yield Static(_row_count_text(len(rows)), classes="row-count")
            with Horizontal(id="buttons"):
                yield from _button_row(button_list)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id and btn_id.startswith("btn_") and btn_id[4:].isdigit():
            idx = int(btn_id.split("_")[1])
            value = self.args.get("button_list", [("Continue", 1)])[idx][1]
            self._result = {"button": value}
            self.dismiss(self._result)


# ---------------------------------------------------------------------------
# FILE / DIRECTORY path dialogs
# ---------------------------------------------------------------------------


class FilePathScreen(_BaseDialog):
    """File/directory path input dialog (no native file browser in TUI)."""

    def __init__(self, args: dict, prompt_text: str, result_key: str) -> None:
        super().__init__(args)
        self._prompt_text = prompt_text
        self._result_key = result_key

    def compose(self) -> ComposeResult:
        working_dir = self.args.get("working_dir", os.getcwd())
        with Container(id="dialog"):
            yield Label(self._prompt_text, id="title")
            yield Static(f"Starting directory: {working_dir}", id="message")
            yield Input(
                placeholder="Type path here...",
                id="path_input",
            )
            with Horizontal(id="buttons"):
                yield Button("OK", id="btn_ok", variant="primary")
                yield Button("Cancel", id="btn_cancel", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_ok":
            value = self.query_one("#path_input", Input).value.strip() or None
        else:
            value = None
        self._result = {self._result_key: value}
        self.dismiss(self._result)


class OpenFileScreen(FilePathScreen):
    def __init__(self, args: dict) -> None:
        super().__init__(args, "Open file", "filename")


class SaveFileScreen(FilePathScreen):
    def __init__(self, args: dict) -> None:
        super().__init__(args, "Save file as", "filename")


class DirectoryScreen(FilePathScreen):
    def __init__(self, args: dict) -> None:
        super().__init__(args, "Select directory", "directory")


# ---------------------------------------------------------------------------
# CREDENTIALS dialog
# ---------------------------------------------------------------------------


class CredentialsScreen(_BaseDialog):
    """Username and password entry dialog."""

    DEFAULT_CSS = (
        _BaseDialog.DEFAULT_CSS
        + """
    .field-row {
        height: 3;
        margin-bottom: 1;
    }
    .field-label {
        width: 12;
        content-align: right middle;
        padding-right: 1;
    }
    """
    )

    def compose(self) -> ComposeResult:
        message = self.args.get("message", "")
        with Container(id="dialog"):
            yield Label("Credentials", id="title")
            if message:
                yield Static(message, id="message")
            with Horizontal(classes="field-row"):
                yield Label("Username:", classes="field-label")
                yield Input(id="username_input", placeholder="Username")
            with Horizontal(classes="field-row"):
                yield Label("Password:", classes="field-label")
                yield Input(id="password_input", password=True, placeholder="Password")
            with Horizontal(id="buttons"):
                yield Button("OK", id="btn_ok", variant="primary")
                yield Button("Cancel", id="btn_cancel", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_ok":
            username = self.query_one("#username_input", Input).value
            password = self.query_one("#password_input", Input).value
            self._result = {"username": username, "password": password}
        else:
            self._result = {"username": "", "password": ""}
        self.dismiss(self._result)


# ---------------------------------------------------------------------------
# CONNECT dialog
# ---------------------------------------------------------------------------


_DB_TYPES = [
    ("p", "PostgreSQL"),
    ("s", "SQL Server"),
    ("l", "SQLite"),
    ("m", "MySQL/MariaDB"),
    ("k", "DuckDB"),
    ("o", "Oracle"),
    ("f", "Firebird"),
    ("a", "MS-Access"),
    ("d", "DSN"),
]


class ConnectScreen(_BaseDialog):
    """Database connection selection dialog."""

    DEFAULT_CSS = (
        _BaseDialog.DEFAULT_CSS
        + """
    .field-row {
        height: 3;
        margin-bottom: 1;
    }
    .field-label {
        width: 14;
        content-align: right middle;
        padding-right: 1;
    }
    """
    )

    def compose(self) -> ComposeResult:
        message = self.args.get("message", "")
        with Container(id="dialog"):
            yield Label("Connect to Database", id="title")
            help_btn = _help_button(self.args.get("help_url"))
            if help_btn:
                yield help_btn
            if message:
                yield Static(message, id="message")
            with Horizontal(classes="field-row"):
                yield Label("Database type:", classes="field-label")
                yield Select(
                    options=[(v, k) for k, v in _DB_TYPES],
                    id="db_type_select",
                )
            with Horizontal(classes="field-row"):
                yield Label("Server:", classes="field-label")
                yield Input(id="server_input", placeholder="Hostname or IP")
            with Horizontal(classes="field-row"):
                yield Label("Database:", classes="field-label")
                yield Input(id="database_input", placeholder="Database name or file path")
            with Horizontal(classes="field-row"):
                yield Label("Username:", classes="field-label")
                yield Input(id="username_input", placeholder="(optional)")
            with Horizontal(id="buttons"):
                yield Button("Connect", id="btn_ok", variant="primary")
                yield Button("Cancel", id="btn_cancel", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_ok":
            db_type_sel = self.query_one("#db_type_select", Select)
            db_type = str(db_type_sel.value) if db_type_sel.value else "l"
            server = self.query_one("#server_input", Input).value.strip() or None
            database = self.query_one("#database_input", Input).value.strip() or None
            username = self.query_one("#username_input", Input).value.strip() or None
            self._result = {
                "db_type": db_type,
                "server": server,
                "database": database,
                "db_file": database if db_type in ("l", "k", "a") else None,
                "username": username,
            }
        else:
            self._result = {"db_type": None}
        self.dismiss(self._result)


# ---------------------------------------------------------------------------
# Screen map: gui_type constant → ModalScreen class
# ---------------------------------------------------------------------------


def _build_screen_map() -> dict:
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
    )

    return {
        GUI_HALT: MsgScreen,
        GUI_MSG: MsgScreen,
        GUI_PAUSE: PauseScreen,
        GUI_DISPLAY: DisplayScreen,
        GUI_ENTRY: EntryFormScreen,
        GUI_COMPARE: CompareScreen,
        GUI_SELECTROWS: SelectRowsScreen,
        GUI_SELECTSUB: SelectSubScreen,
        GUI_ACTION: ActionScreen,
        GUI_MAP: MapScreen,
        GUI_OPENFILE: OpenFileScreen,
        GUI_SAVEFILE: SaveFileScreen,
        GUI_DIRECTORY: DirectoryScreen,
        GUI_CREDENTIALS: CredentialsScreen,
        GUI_CONNECT: ConnectScreen,
        # QUERY_CONSOLE is handled inline in ConductorApp._handle_spec
    }


# ---------------------------------------------------------------------------
# _SingleDialogApp — short-lived Textual app for one dialog
# ---------------------------------------------------------------------------


class _SingleDialogApp(App):
    """Runs a single ModalScreen dialog, returns its result, then exits.

    Used by ``_run_dialog_sync`` to show a dialog from the main thread without
    maintaining a persistent Textual app between dialogs.  The terminal is only
    in Textual's control for the duration of the dialog.
    """

    DEFAULT_CSS = "Screen { background: $background; }"

    def __init__(self, screen_class: type, args: dict) -> None:
        super().__init__()
        self._screen_class = screen_class
        self._screen_args = args

    def compose(self) -> ComposeResult:
        # Blank base screen — the dialog is pushed immediately on mount.
        yield Static("")

    def on_mount(self) -> None:
        # push_screen with a callback avoids the worker requirement of
        # push_screen_wait; the callback fires when the screen is dismissed.
        self.push_screen(self._screen_class(self._screen_args), self._on_result)

    def _on_result(self, result: Any) -> None:
        self.exit(result)


# ---------------------------------------------------------------------------
# _TextualSyncQueue — synchronous gui_manager_queue replacement
# ---------------------------------------------------------------------------


class _TextualSyncQueue:
    """Drop-in replacement for ``_state.gui_manager_queue`` on the Textual path.

    gui_level >= 1 with Textual installed: instead of an async manager thread,
    ``put()`` runs the dialog synchronously in the main thread by launching a
    short-lived ``_SingleDialogApp``.  After ``put()`` returns, the result is
    already on ``spec.return_queue`` so the calling metacommand's ``get()``
    unblocks immediately.
    """

    _screen_map: dict | None = None

    def put(self, spec: Any, block: bool = True, timeout: Any = None) -> None:
        if spec is None:
            return
        from execsql.utils.gui import QUERY_CONSOLE

        if spec.gui_type == QUERY_CONSOLE:
            spec.return_queue.put({"console_running": False})
            return
        if self._screen_map is None:
            self.__class__._screen_map = _build_screen_map()
        screen_class = self._screen_map.get(spec.gui_type)
        if screen_class is None:
            spec.return_queue.put({"error": f"Unknown GUI type: {spec.gui_type}", "button": None})
            return
        try:
            result = _SingleDialogApp(screen_class, spec.args).run()
        except Exception as exc:
            spec.return_queue.put({"error": str(exc), "button": None})
            return
        if result is not None and result.get("cancelled"):
            raise SystemExit(2)
        spec.return_queue.put(result if result is not None else {})

    def get_nowait(self) -> Any:
        raise _stdlib_queue.Empty

    def get(self, block: bool = True, timeout: Any = None) -> Any:
        raise _stdlib_queue.Empty


# ---------------------------------------------------------------------------
# _ConsoleDialogQueue — thread-safe queue for ConsoleApp dialog dispatch
# ---------------------------------------------------------------------------


class _ConsoleDialogQueue:
    """Queue used by the script worker thread to request GUI dialogs.

    The worker thread deposits ``GuiSpec`` objects via ``put()`` and then
    blocks on ``spec.return_queue.get()``.  ``ConsoleApp``'s timer poller
    processes them in the main Textual thread via ``push_screen_wait()``.
    """

    def __init__(self) -> None:
        self._q: _stdlib_queue.Queue = _stdlib_queue.Queue()

    def put(self, spec: Any, block: bool = True, timeout: Any = None) -> None:
        if spec is None:
            return
        self._q.put(spec, block=block, timeout=timeout)

    def get_nowait(self) -> Any:
        return self._q.get_nowait()

    def get(self, block: bool = True, timeout: Any = None) -> Any:
        return self._q.get(block=block, timeout=timeout)


# ---------------------------------------------------------------------------
# ConsoleApp — persistent Textual app for gui_level 3
# ---------------------------------------------------------------------------


class ConsoleApp(App):
    """Persistent Textual console for gui_level 3.

    The SQL script runs in a background worker thread.  This app runs in the
    main thread (required by Textual / signal handling).  Output from the
    script reaches the ``RichLog`` widget via ``write_console()`` which is
    called from the worker thread using ``call_from_thread()``.

    Dialog requests from metacommands are deposited onto ``dialog_queue`` by
    the worker thread; a timer polls the queue every 50 ms and serves each
    request as a ``ModalScreen`` overlay via ``push_screen_wait()``.
    """

    BINDINGS = [Binding("ctrl+c", "request_quit", "Quit", show=True)]

    DEFAULT_CSS = """
    ConsoleApp {
        background: $background;
    }
    #console_log {
        height: 1fr;
        border: none;
    }
    #status_bar {
        height: 1;
        background: $panel;
        padding: 0 1;
    }
    #progress_bar {
        width: 20;
        height: 1;
    }
    #footer_row {
        height: 1;
        background: $panel;
    }
    """

    def __init__(
        self,
        script_runner: Any,
        dialog_queue: _ConsoleDialogQueue,
        wait_on_exit: bool = False,
    ) -> None:
        super().__init__()
        self._script_runner = script_runner
        self._dialog_queue = dialog_queue
        self._wait_on_exit = wait_on_exit
        self._script_thread: threading.Thread | None = None
        self._script_exception: BaseException | None = None
        self._screen_map: dict | None = None
        self._console_lines: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield RichLog(id="console_log", highlight=True, markup=True, wrap=True)
        with Horizontal(id="footer_row"):
            yield Label("Running…", id="status_bar")
            yield ProgressBar(id="progress_bar", total=100, show_eta=False)
        yield Footer()

    def on_mount(self) -> None:
        self._script_thread = threading.Thread(
            target=self._run_script,
            daemon=True,
            name="execsql-script",
        )
        self._script_thread.start()
        self.set_interval(0.05, self._poll_dialog_queue)

    def _run_script(self) -> None:
        try:
            self._script_runner()
        except BaseException as exc:
            self._script_exception = exc
        finally:
            self.call_from_thread(self._on_script_done)

    def _on_script_done(self) -> None:
        if self._wait_on_exit:
            self.query_one("#status_bar", Label).update(
                "Script complete — press Ctrl+C or close window to exit.",
            )
        else:
            self.exit()

    def _poll_dialog_queue(self) -> None:
        try:
            spec = self._dialog_queue.get_nowait()
        except _stdlib_queue.Empty:
            return
        from execsql.utils.gui import QUERY_CONSOLE

        if spec.gui_type == QUERY_CONSOLE:
            spec.return_queue.put({"console_running": True})
            return
        if self._screen_map is None:
            self._screen_map = _build_screen_map()
        screen_class = self._screen_map.get(spec.gui_type)
        if screen_class is None:
            spec.return_queue.put({"error": f"Unknown GUI type: {spec.gui_type}", "button": None})
            return

        async def _push() -> None:
            result = await self.push_screen_wait(screen_class(spec.args))
            if result is not None and result.get("cancelled"):
                # Interrupt the worker thread
                if self._script_thread and self._script_thread.is_alive():
                    tid = self._script_thread.ident
                    if tid is not None:
                        ctypes.pythonapi.PyThreadState_SetAsyncExc(
                            ctypes.c_ulong(tid),
                            ctypes.py_object(SystemExit),
                        )
                spec.return_queue.put(result if result is not None else {})
            else:
                spec.return_queue.put(result if result is not None else {})

        self.run_worker(_push, exclusive=False)

    def write_console(self, text: str) -> None:
        """Thread-safe method to append text to the RichLog widget."""
        self.call_from_thread(self._append_console, text)

    def _append_console(self, text: str) -> None:
        self._console_lines.append(text)
        try:
            self.query_one("#console_log", RichLog).write(text)
        except Exception:
            pass  # Widget may not be mounted yet.

    def save(self, outfile: str, append: bool = False) -> None:
        """Save the console text contents to *outfile*."""
        mode = "a" if append else "w"
        with open(outfile, mode, encoding="utf-8") as fh:
            for line in self._console_lines:
                fh.write(line if line.endswith("\n") else line + "\n")

    def set_status(self, msg: str) -> None:
        """Thread-safe status bar update."""
        self.call_from_thread(self._update_status, msg)

    def _update_status(self, msg: str) -> None:
        try:
            self.query_one("#status_bar", Label).update(msg)
        except Exception:
            pass  # Widget may not be mounted yet.

    def set_progress(self, pct: float) -> None:
        """Thread-safe progress bar update (0–100)."""
        self.call_from_thread(self._update_progress, pct)

    def _update_progress(self, pct: float) -> None:
        try:
            self.query_one("#progress_bar", ProgressBar).progress = max(0.0, min(100.0, pct))
        except Exception:
            pass  # Widget may not be mounted yet.

    def action_request_quit(self) -> None:
        if self._script_thread and self._script_thread.is_alive():
            tid = self._script_thread.ident
            if tid is not None:
                ctypes.pythonapi.PyThreadState_SetAsyncExc(
                    ctypes.c_ulong(tid),
                    ctypes.py_object(SystemExit),
                )
        self.exit()


# ---------------------------------------------------------------------------
# TextualBackend
# ---------------------------------------------------------------------------


class TextualBackend(GuiBackend):
    """GUI backend for the Textual path (gui_level 1 or 2).

    Dialog dispatch goes through ``_TextualSyncQueue`` (set as
    ``_state.gui_manager_queue`` by ``enable_gui()``), so the ``show_*``
    methods below are the canonical implementations — called by
    ``gui_manager_loop`` via ``dispatch()`` — but only used when the
    thread-based manager path is taken (which it isn't for Textual; the sync
    queue handles everything).  They are implemented here to satisfy the ABC
    and in case the backend is ever called directly.
    """

    def __init__(self) -> None:
        self._console_running = False
        self._console_app: ConsoleApp | None = None

    def query_console(self, args: dict) -> dict:
        return {"console_running": self._console_running}

    def console_on(self) -> None:
        self._console_running = True
        self._console_app = None

    def console_off(self) -> None:
        self._console_running = False
        self._console_app = None
        import execsql.state as _state

        if _state.output is not None:
            _state.output.reset()

    def console_status(self, message: str) -> None:
        if self._console_app is not None:
            self._console_app.set_status(message)

    def console_progress(self, num: float, total: float | None = None) -> None:
        if self._console_app is not None:
            pct = (num / total * 100.0) if total else num
            self._console_app.set_progress(pct)

    def console_save(self, outfile: str, append: bool = False) -> None:
        """Save console text contents to *outfile*."""
        if self._console_app is not None:
            self._console_app.save(outfile, append)

    def console_hide(self) -> None:
        """Hide the console (minimize) — Textual has no window-level hide,
        so this is a no-op in a terminal environment."""

    def console_show(self) -> None:
        """Show the console — Textual has no window-level show,
        so this is a no-op in a terminal environment."""

    def console_wait_user(self, message: str = "") -> None:
        # ConsoleApp exits when the script is done; nothing extra needed here.
        pass

    def _run(self, screen_class: type, args: dict) -> dict:
        result = _SingleDialogApp(screen_class, args).run()
        return result if result is not None else {}

    def show_halt(self, args: dict) -> dict:
        return self._run(MsgScreen, args)

    def show_msg(self, args: dict) -> dict:
        return self._run(MsgScreen, args)

    def show_pause(self, args: dict) -> dict:
        return self._run(PauseScreen, args)

    def show_display(self, args: dict) -> dict:
        return self._run(DisplayScreen, args)

    def show_entry_form(self, args: dict) -> dict:
        return self._run(EntryFormScreen, args)

    def show_compare(self, args: dict) -> dict:
        return self._run(CompareScreen, args)

    def show_select_rows(self, args: dict) -> dict:
        return self._run(SelectRowsScreen, args)

    def show_select_sub(self, args: dict) -> dict:
        return self._run(SelectSubScreen, args)

    def show_action(self, args: dict) -> dict:
        return self._run(ActionScreen, args)

    def show_map(self, args: dict) -> dict:
        return self._run(MapScreen, args)

    def show_open_file(self, args: dict) -> dict:
        return self._run(OpenFileScreen, args)

    def show_save_file(self, args: dict) -> dict:
        return self._run(SaveFileScreen, args)

    def show_directory(self, args: dict) -> dict:
        return self._run(DirectoryScreen, args)

    def show_credentials(self, args: dict) -> dict:
        return self._run(CredentialsScreen, args)

    def show_connect(self, args: dict) -> dict:
        return self._run(ConnectScreen, args)
