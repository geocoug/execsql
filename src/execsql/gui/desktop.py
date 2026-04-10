"""Tkinter desktop GUI backend for execsql.

Ported from the original execsql monolith (_execsql/execsql.py).
Uses Python's built-in tkinter — no extra dependencies required.

Note: On macOS, Tkinter requires that dialogs run in the main thread.
      When running execsql in headless/server mode, use the TUI backend instead.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

from execsql.gui.base import GuiBackend

# ---------------------------------------------------------------------------
# Tkinter import guard
# ---------------------------------------------------------------------------
try:
    import tkinter as tk
    from tkinter import filedialog, scrolledtext, ttk
except ImportError as _e:
    raise ImportError(
        "tkinter is not available on this Python installation.",
    ) from _e

__all__ = ["TkinterBackend"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WINDOW_BG = "#f0f0f0"
_TABLE_FONT = ("Courier", 10)
_CONSOLE_FONT = ("Courier", 12)
_LABEL_FONT = ("TkDefaultFont", 10)
_TITLE_FONT = ("TkDefaultFont", 11, "bold")


def _center_window(win: tk.Tk | tk.Toplevel, width: int = 600, height: int = 400) -> None:
    """Center a window on the screen."""
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    x = (sw - width) // 2
    y = (sh - height) // 2
    win.geometry(f"{width}x{height}+{x}+{y}")


from execsql.gui.base import DIFF_MARKER, compare_stats as _compare_stats, compute_row_diffs


def _add_help_button(frame: tk.Frame, url: str | None) -> None:
    """Add a Help button to the top-right of *frame* that opens *url* in the system browser.

    Uses ``place()`` so the button overlays the top-right corner without
    consuming vertical space in the pack/grid layout.
    """
    if url:
        import webbrowser

        btn = ttk.Button(frame, text="Help", command=lambda: webbrowser.open(url))
        btn.place(relx=1.0, x=-4, y=4, anchor="ne")


def _row_count_text(n: int) -> str:
    """Return a human-readable row count string, e.g. '3 rows' or '1 row'."""
    return f"{n:,} row{'s' if n != 1 else ''}"


def _populate_treeview(tree: ttk.Treeview, headers: list, rows: list) -> None:
    """Fill a ttk.Treeview with column headers and data rows."""
    tree["columns"] = [str(h) for h in headers]
    tree["show"] = "headings"
    for h in headers:
        tree.heading(str(h), text=str(h))
        tree.column(str(h), width=max(80, len(str(h)) * 9), minwidth=40)
    for row in rows:
        tree.insert("", "end", values=[str(c) if c is not None else "" for c in row])


def _add_buttons(frame: tk.Frame, button_list: list, callback) -> None:
    """Add buttons from button_list = [(label, value, key?), ...] to frame."""
    for _i, btn in enumerate(button_list):
        label = btn[0]
        value = btn[1]
        b = tk.Button(frame, text=label, command=lambda v=value: callback(v), padx=8)
        b.pack(side=tk.LEFT, padx=4)
        if len(btn) > 2 and btn[2]:
            key_seq = btn[2]
            if key_seq == "<Return>":
                frame.winfo_toplevel().bind("<Return>", lambda e, v=value: callback(v))
            elif len(key_seq) == 1:
                frame.winfo_toplevel().bind(key_seq, lambda e, v=value: callback(v))


# ---------------------------------------------------------------------------
# MsgDialog — simple message
# ---------------------------------------------------------------------------


class MsgDialog:
    def __init__(self, root: tk.Tk, args: dict) -> None:
        self.result: dict = {}
        win = tk.Toplevel(root)
        win.title(args.get("title", "Message"))
        win.grab_set()

        frame = ttk.Frame(win, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text=args.get("message", ""), wraplength=480, anchor="w", justify="left").pack(
            anchor="w",
            pady=(0, 12),
        )

        headers = args.get("column_headers")
        rows = args.get("rowset")
        if headers and rows:
            tree = ttk.Treeview(frame, height=min(8, len(rows)))
            _populate_treeview(tree, headers, rows)
            vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
            tree.configure(yscrollcommand=vsb.set)
            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            vsb.pack(side=tk.RIGHT, fill=tk.Y)
            ttk.Label(frame, text=_row_count_text(len(rows))).pack(anchor="w")

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=8, anchor="e")
        ttk.Button(btn_frame, text="Close", command=lambda: self._close(win, 1)).pack()
        win.bind("<Return>", lambda e: self._close(win, 1))
        win.bind("<Escape>", lambda e: self._close(win, 1))
        _center_window(win)
        root.wait_window(win)

    def _close(self, win: tk.Toplevel, value: int) -> None:
        self.result = {"button": value}
        win.destroy()


# ---------------------------------------------------------------------------
# PauseDialog
# ---------------------------------------------------------------------------


class PauseDialog:
    def __init__(self, root: tk.Tk, args: dict) -> None:
        self.result: dict = {}
        self._quit = False

        win = tk.Toplevel(root)
        win.title(args.get("title", "Pause"))
        win.grab_set()

        frame = ttk.Frame(win, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text=args.get("message", ""), wraplength=480, anchor="w", justify="left").pack(
            anchor="w",
            pady=(0, 12),
        )

        countdown = args.get("countdown")
        self._remaining = countdown

        status_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=status_var).pack()

        progress = ttk.Progressbar(frame, maximum=100, mode="determinate")
        progress.pack(fill=tk.X, pady=4)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=8, anchor="e")
        ttk.Button(btn_frame, text="Continue", command=lambda: self._close(win, False)).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel", command=lambda: self._close(win, True)).pack(side=tk.LEFT, padx=4)
        win.bind("<Return>", lambda e: self._close(win, False))
        win.bind("<Escape>", lambda e: self._close(win, True))
        _center_window(win, 400, 200)

        if countdown is not None:
            total = float(countdown)
            start = time.time()

            def _tick():
                elapsed = time.time() - start
                remaining = max(0.0, total - elapsed)
                pct = (elapsed / total * 100) if total > 0 else 100
                progress["value"] = pct
                status_var.set(f"{remaining:.0f}s remaining")
                if remaining <= 0:
                    self._close(win, False)
                elif win.winfo_exists():
                    win.after(200, _tick)

            win.after(200, _tick)

        root.wait_window(win)

    def _close(self, win: tk.Toplevel, quit: bool) -> None:
        self.result = {"quit": quit}
        if win.winfo_exists():
            win.destroy()


# ---------------------------------------------------------------------------
# DisplayDialog — data table + optional text entry + buttons
# ---------------------------------------------------------------------------


class DisplayDialog:
    def __init__(self, root: tk.Tk, args: dict) -> None:
        self.result: dict = {}

        win = tk.Toplevel(root)
        win.title(args.get("title", ""))
        win.grab_set()

        frame = ttk.Frame(win, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        _add_help_button(frame, args.get("help_url"))

        message = args.get("message", "")
        if message:
            ttk.Label(frame, text=message, wraplength=580, anchor="w", justify="left").pack(
                anchor="w",
                pady=(0, 8),
            )

        headers = args.get("column_headers")
        rows = args.get("rowset")
        if headers and rows:
            table_frame = ttk.Frame(frame)
            table_frame.pack(fill=tk.BOTH, expand=True)
            tree = ttk.Treeview(table_frame, height=min(10, len(rows)))
            _populate_treeview(tree, headers, rows)
            vsb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=tree.yview)
            hsb = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=tree.xview)
            tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
            tree.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")
            table_frame.rowconfigure(0, weight=1)
            table_frame.columnconfigure(0, weight=1)
            ttk.Label(frame, text=_row_count_text(len(rows))).pack(anchor="w")

        self._text_var = None
        textentry = args.get("textentry", False)
        hidetext = args.get("hidetext", False)
        initial = args.get("initialtext", "")
        if textentry:
            entry_frame = ttk.Frame(frame)
            entry_frame.pack(fill=tk.X, pady=8)
            ttk.Label(entry_frame, text="Value:").pack(side=tk.LEFT, padx=4)
            self._text_var = tk.StringVar(value=initial)
            show = "*" if hidetext else ""
            ttk.Entry(entry_frame, textvariable=self._text_var, show=show, width=40).pack(side=tk.LEFT)

        button_list = args.get("button_list", [("Continue", 1, "<Return>")])
        no_cancel = args.get("no_cancel", False)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=8, anchor="e")
        _add_buttons(btn_frame, button_list, lambda v: self._close(win, v))
        if not no_cancel:
            win.bind("<Escape>", lambda e: self._close(win, None))

        _center_window(win, 640, 400)
        root.wait_window(win)

    def _close(self, win: tk.Toplevel, value: int | None) -> None:
        self.result = {
            "button": value,
            "return_value": self._text_var.get() if self._text_var else None,
        }
        if win.winfo_exists():
            win.destroy()


# ---------------------------------------------------------------------------
# EntryFormDialog — multi-field form
# ---------------------------------------------------------------------------


class EntryFormDialog:
    def __init__(self, root: tk.Tk, args: dict) -> None:
        self.result: dict = {}
        self._widgets: dict[str, Any] = {}

        win = tk.Toplevel(root)
        win.title(args.get("title", "Entry"))
        win.grab_set()

        main_frame = ttk.Frame(win, padding=12)
        main_frame.pack(fill=tk.BOTH, expand=True)
        _add_help_button(main_frame, args.get("help_url"))

        message = args.get("message", "")
        if message:
            ttk.Label(main_frame, text=message, wraplength=580, anchor="w", justify="left").pack(
                anchor="w",
                pady=(0, 8),
            )

        headers = args.get("column_headers")
        rows = args.get("rowset")
        if headers and rows:
            tree = ttk.Treeview(main_frame, height=min(6, len(rows)))
            _populate_treeview(tree, headers, rows)
            tree.pack(fill=tk.BOTH, expand=True, pady=(0, 4))
            ttk.Label(main_frame, text=_row_count_text(len(rows))).pack(anchor="w", pady=(0, 8))

        specs = args.get("entry_specs", [])
        form_frame = ttk.Frame(main_frame)
        form_frame.pack(fill=tk.BOTH, expand=True)

        for i, spec in enumerate(specs):
            etype = (spec.entry_type or "text").lower()
            # For radiobuttons, the label is semicolon-delimited: first part is the label
            if etype == "radiobuttons":
                parts = (spec.label or "").split(";")
                field_label = parts[0].strip() if parts else spec.varname
            else:
                field_label = spec.label or spec.varname
            ttk.Label(form_frame, text=field_label, anchor="e").grid(
                row=i,
                column=0,
                sticky="ne",
                padx=4,
                pady=2,
            )
            if etype == "checkbox":
                var = tk.BooleanVar(value=(spec.initial_value or "").lower() in ("true", "1", "yes"))
                cb = ttk.Checkbutton(form_frame, variable=var)
                cb.grid(row=i, column=1, sticky="w", pady=2)
                self._widgets[spec.varname] = ("checkbox", var)
            elif etype in ("dropdown", "select") and spec.lookup_list:
                var = tk.StringVar(value=spec.initial_value or (spec.lookup_list[0] if spec.lookup_list else ""))
                combo = ttk.Combobox(form_frame, textvariable=var, values=spec.lookup_list, state="readonly")
                combo.grid(row=i, column=1, sticky="ew", pady=2)
                self._widgets[spec.varname] = ("dropdown", var)
            elif etype == "listbox" and spec.lookup_list:
                height = spec.default_height or 4
                lb = tk.Listbox(form_frame, selectmode=tk.MULTIPLE, height=height, exportselection=False)
                for item in spec.lookup_list:
                    lb.insert(tk.END, item)
                lb.grid(row=i, column=1, sticky="ew", pady=2)
                self._widgets[spec.varname] = ("listbox", lb)
            elif etype == "radiobuttons":
                buttons = parts[1:] if len(parts) > 1 else ["Option"]
                var = tk.IntVar(value=0)
                rb_frame = ttk.Frame(form_frame)
                rb_frame.grid(row=i, column=1, sticky="w", pady=2)
                for j, btn_label in enumerate(buttons):
                    ttk.Radiobutton(rb_frame, text=btn_label.strip(), variable=var, value=j).pack(anchor="w")
                self._widgets[spec.varname] = ("radiobuttons", var)
            elif etype == "textarea":
                height = spec.default_height or 5
                ta = tk.Text(form_frame, width=40, height=height, wrap=tk.WORD)
                if spec.initial_value:
                    ta.insert("1.0", spec.initial_value)
                ta.grid(row=i, column=1, sticky="ew", pady=2)
                self._widgets[spec.varname] = ("textarea", ta)
            elif etype in ("inputfile", "outputfile"):
                file_frame = ttk.Frame(form_frame)
                file_frame.grid(row=i, column=1, sticky="ew", pady=2)
                var = tk.StringVar(value=spec.initial_value or "")
                ttk.Entry(file_frame, textvariable=var, width=30).pack(side=tk.LEFT, fill=tk.X, expand=True)

                def _browse(sv=var, mode=etype):
                    from tkinter import filedialog

                    if mode == "inputfile":
                        fn = filedialog.askopenfilename()
                    else:
                        fn = filedialog.asksaveasfilename()
                    if fn:
                        sv.set(fn)

                ttk.Button(file_frame, text="Browse…", command=_browse).pack(side=tk.LEFT, padx=(4, 0))
                self._widgets[spec.varname] = ("file", var)
            else:
                var = tk.StringVar(value=spec.initial_value or "")
                entry = ttk.Entry(form_frame, textvariable=var, width=40)
                if spec.validation_key_regex:
                    import re as _re

                    _pat = _re.compile(spec.validation_key_regex)
                    vcmd = (win.register(lambda val, p=_pat: bool(p.match(val))), "%P")
                    entry.configure(validate="key", validatecommand=vcmd)
                entry.grid(row=i, column=1, sticky="ew", pady=2)
                self._widgets[spec.varname] = ("text", var)
            form_frame.columnconfigure(1, weight=1)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=8, anchor="e")
        ttk.Button(btn_frame, text="OK", command=lambda: self._close(win, specs, True)).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel", command=lambda: self._close(win, specs, False)).pack(side=tk.LEFT, padx=4)
        win.bind("<Return>", lambda e: self._close(win, specs, True))
        win.bind("<Escape>", lambda e: self._close(win, specs, False))

        self._specs = specs
        extra_height = sum(
            (spec.default_height or 5) * 18 if (spec.entry_type or "").lower() in ("textarea", "listbox") else 0
            for spec in specs
        )
        _center_window(win, 500, 120 + len(specs) * 32 + extra_height)
        root.wait_window(win)

    def _close(self, win: tk.Toplevel, specs: list, ok: bool) -> None:
        if ok:
            import re as _re

            for spec in specs:
                entry = self._widgets.get(spec.varname)
                if entry is None:
                    continue
                kind, var = entry
                if kind == "checkbox":
                    spec.value = "1" if var.get() else "0"
                elif kind == "listbox":
                    selected = [var.get(i) for i in var.curselection()]
                    spec.value = ",".join(f"'{v.replace(chr(39), chr(39) + chr(39))}'" for v in selected)
                elif kind == "radiobuttons":
                    spec.value = str(var.get() + 1)
                elif kind == "textarea":
                    spec.value = var.get("1.0", tk.END).rstrip("\n")
                else:
                    spec.value = var.get()
            # Validate required fields and validation_regex
            errors = []
            for spec in specs:
                val = spec.value or ""
                etype = (spec.entry_type or "text").lower()
                if spec.required and not val and etype != "checkbox":
                    errors.append(f"{spec.label or spec.varname}: required")
                if spec.validation_regex and val and not _re.fullmatch(spec.validation_regex, val):
                    errors.append(f"{spec.label or spec.varname}: does not match pattern")
            if errors:
                from tkinter import messagebox

                messagebox.showerror("Validation Error", "\n".join(errors), parent=win)
                return
            self.result = {"button": 1, "return_value": specs}
        else:
            self.result = {"button": None, "return_value": specs}
        if win.winfo_exists():
            win.destroy()


# ---------------------------------------------------------------------------
# CompareDialog
# ---------------------------------------------------------------------------


class CompareDialog:
    def __init__(self, root: tk.Tk, args: dict) -> None:
        self.result: dict = {}

        win = tk.Toplevel(root)
        win.title(args.get("title", "Compare"))
        win.grab_set()

        frame = ttk.Frame(win, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        _add_help_button(frame, args.get("help_url"))

        message = args.get("message", "")
        if message:
            ttk.Label(frame, text=message, wraplength=780, anchor="w", justify="left").pack(
                anchor="w",
                pady=(0, 8),
            )

        headers1 = args.get("headers1", [])
        rows1 = args.get("rows1", [])
        headers2 = args.get("headers2", [])
        rows2 = args.get("rows2", [])
        keylist = [str(k) for k in args.get("keylist", [])]
        sidebyside = args.get("sidebyside", True)

        # Reserve a frame for the diff button (packed before tables, populated after)
        diff_frame = ttk.Frame(frame) if keylist else None
        if diff_frame:
            diff_frame.pack(anchor="w", pady=(0, 4))

        tables_frame = ttk.Frame(frame)
        tables_frame.pack(fill=tk.BOTH, expand=True)

        pack_side = tk.LEFT if sidebyside else tk.TOP
        max_tree_height = 12 if sidebyside else 8

        def _add_tree(parent, label, headers, rows):
            lf = ttk.LabelFrame(parent, text=label)
            lf.pack(side=pack_side, fill=tk.BOTH, expand=True, padx=4, pady=2)
            tree_frame = ttk.Frame(lf)
            tree_frame.pack(fill=tk.BOTH, expand=True)
            tree = ttk.Treeview(tree_frame, height=min(max_tree_height, len(rows)))
            _populate_treeview(tree, headers, rows)
            vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
            tree.configure(yscrollcommand=vsb.set)
            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            vsb.pack(side=tk.RIGHT, fill=tk.Y)
            ttk.Label(lf, text=_row_count_text(len(rows))).pack(anchor="w")
            return tree

        tree1 = _add_tree(tables_frame, "Table 1", headers1, rows1)
        tree2 = _add_tree(tables_frame, "Table 2", headers2, rows2)

        # Cross-table row highlighting based on key columns
        if keylist:
            headers1_str = [str(h) for h in headers1]
            headers2_str = [str(h) for h in headers2]
            key_idx1 = [i for i, h in enumerate(headers1_str) if h in keylist]
            key_idx2 = [i for i, h in enumerate(headers2_str) if h in keylist]

            # Syncing uses display-consistent string normalization (treeview
            # values are strings).  The diff engine in base.py has its own
            # _pk_tuple with native-equality semantics — it does not share
            # these maps.
            def _kv(row, idxs):
                return tuple(str(row[i]) if row[i] is not None else "" for i in idxs)

            iids1 = tree1.get_children()
            iids2 = tree2.get_children()
            iid_to_kv1 = {iid: _kv(rows1[i], key_idx1) for i, iid in enumerate(iids1)}
            iid_to_kv2 = {iid: _kv(rows2[i], key_idx2) for i, iid in enumerate(iids2)}
            # First occurrence wins for duplicate PKs (consistent with compute_row_diffs).
            kv_to_iid1: dict[tuple, str] = {}
            for iid, kv in iid_to_kv1.items():
                if kv not in kv_to_iid1:
                    kv_to_iid1[kv] = iid
            kv_to_iid2: dict[tuple, str] = {}
            for iid, kv in iid_to_kv2.items():
                if kv not in kv_to_iid2:
                    kv_to_iid2[kv] = iid

            def _on_click1(event):
                sel_item = tree1.focus()
                if not sel_item:
                    return
                match = kv_to_iid2.get(iid_to_kv1.get(sel_item))
                if match:
                    tree2.selection_set(match)
                    tree2.see(match)

            def _on_click2(event):
                sel_item = tree2.focus()
                if not sel_item:
                    return
                match = kv_to_iid1.get(iid_to_kv2.get(sel_item))
                if match:
                    tree1.selection_set(match)
                    tree1.see(match)

            tree1.bind("<ButtonRelease-1>", _on_click1)
            tree2.bind("<ButtonRelease-1>", _on_click2)

        # --- Highlight Diffs button (populate the pre-created diff_frame) ---
        if keylist and diff_frame is not None:
            tree1.tag_configure("diff_match", background="#a3d9a5", foreground="#1a3a1a")
            tree1.tag_configure("diff_changed", background="#f5d98e", foreground="#3a2e00")
            tree1.tag_configure("diff_only", background="#f5a3a3", foreground="#3a0a0a")
            tree2.tag_configure("diff_match", background="#a3d9a5", foreground="#1a3a1a")
            tree2.tag_configure("diff_changed", background="#f5d98e", foreground="#3a2e00")
            tree2.tag_configure("diff_only", background="#f5a3a3", foreground="#3a0a0a")
            _diff_on = [False]
            _diff_result = compute_row_diffs(headers1, rows1, headers2, rows2, keylist)
            _original_values1: dict[str, tuple] = {}
            _original_values2: dict[str, tuple] = {}

            def _apply_diffs(
                tree: ttk.Treeview,
                iids: tuple,
                row_states: list[str],
                changed_cols: list[set[str]],
                headers_str: list[str],
                originals: dict[str, tuple],
                turn_on: bool,
            ) -> None:
                iids_list = list(iids)
                if not turn_on:
                    for iid in iids:
                        tree.item(iid, tags=())
                        if iid in originals:
                            tree.item(iid, values=originals[iid])
                    originals.clear()
                    return
                for iid in iids:
                    ridx = iids_list.index(iid)
                    state = row_states[ridx]
                    if state == "only_t1" or state == "only_t2":
                        tree.item(iid, tags=("diff_only",))
                    elif state == "match":
                        tree.item(iid, tags=("diff_match",))
                    elif state == "changed":
                        tree.item(iid, tags=("diff_changed",))
                        originals[iid] = tree.item(iid, "values")
                        vals = list(tree.item(iid, "values"))
                        diff_set = changed_cols[ridx]
                        for ci, col_name in enumerate(headers_str):
                            if col_name in diff_set and ci < len(vals):
                                vals[ci] = f"{DIFF_MARKER}{vals[ci]}"
                        tree.item(iid, values=vals)

            def _toggle_diffs():
                _diff_on[0] = not _diff_on[0]
                if _diff_result is None:
                    return
                _apply_diffs(
                    tree1,
                    iids1,
                    _diff_result.table1_row_states,
                    _diff_result.table1_changed_cols,
                    [str(h) for h in headers1],
                    _original_values1,
                    _diff_on[0],
                )
                _apply_diffs(
                    tree2,
                    iids2,
                    _diff_result.table2_row_states,
                    _diff_result.table2_changed_cols,
                    [str(h) for h in headers2],
                    _original_values2,
                    _diff_on[0],
                )

            ttk.Button(diff_frame, text="Highlight Diffs", command=_toggle_diffs).pack(side=tk.LEFT)
            ttk.Label(diff_frame, text="  ").pack(side=tk.LEFT)
            tk.Label(diff_frame, text=" Match ", bg="#a3d9a5", fg="#1a3a1a", padx=4).pack(side=tk.LEFT, padx=2)
            tk.Label(diff_frame, text=" Changed ", bg="#f5d98e", fg="#3a2e00", padx=4).pack(side=tk.LEFT, padx=2)
            tk.Label(diff_frame, text=" Only in one ", bg="#f5a3a3", fg="#3a0a0a", padx=4).pack(side=tk.LEFT, padx=2)

        summary = _compare_stats(headers1, rows1, headers2, rows2, keylist)
        if summary:
            ttk.Label(frame, text=summary).pack(anchor="w", pady=(4, 0))

        button_list = args.get("button_list", [("Continue", 1, "<Return>")])
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=8, anchor="e")
        _add_buttons(btn_frame, button_list, lambda v: self._close(win, v))
        win.bind("<Escape>", lambda e: self._close(win, None))

        win_height = 700 if not sidebyside else 500
        _center_window(win, 900, win_height)
        root.wait_window(win)

    def _close(self, win: tk.Toplevel, value: int | None) -> None:
        self.result = {"button": value}
        if win.winfo_exists():
            win.destroy()


# ---------------------------------------------------------------------------
# SelectRowsDialog
# ---------------------------------------------------------------------------


class SelectRowsDialog:
    def __init__(self, root: tk.Tk, args: dict) -> None:
        self.result: dict = {}

        win = tk.Toplevel(root)
        win.title(args.get("title", "Select rows"))
        win.grab_set()

        frame = ttk.Frame(win, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        _add_help_button(frame, args.get("help_url"))

        message = args.get("message", "")
        if message:
            ttk.Label(frame, text=message, wraplength=780, anchor="w", justify="left").pack(
                anchor="w",
                pady=(0, 4),
            )
        ttk.Label(frame, text="Double-click a row to copy it to the destination table.").pack(
            anchor="w",
            pady=(0, 8),
        )

        headers1 = args.get("headers1", [])
        rows1 = args.get("rows1", [])
        headers2 = args.get("headers2", [])
        rows2 = args.get("rows2", [])

        tables_frame = ttk.Frame(frame)
        tables_frame.pack(fill=tk.BOTH, expand=True)

        def _add_tree_frame(parent, label, headers, rows):
            lf = ttk.LabelFrame(parent, text=label)
            lf.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
            tree_frame = ttk.Frame(lf)
            tree_frame.pack(fill=tk.BOTH, expand=True)
            tree = ttk.Treeview(tree_frame, height=min(12, max(len(rows1), len(rows2))))
            _populate_treeview(tree, headers, rows)
            vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
            tree.configure(yscrollcommand=vsb.set)
            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            vsb.pack(side=tk.RIGHT, fill=tk.Y)
            ttk.Label(lf, text=_row_count_text(len(rows))).pack(anchor="w")
            return tree

        src_tree = _add_tree_frame(tables_frame, "Source", headers1, rows1)
        dst_tree = _add_tree_frame(tables_frame, "Destination", headers2, rows2)

        def _on_double_click(event):
            sel = src_tree.selection()
            if sel:
                row_id = sel[0]
                values = src_tree.item(row_id, "values")
                dst_tree.insert("", "end", values=values)

        src_tree.bind("<Double-1>", _on_double_click)
        src_tree.bind("<Return>", _on_double_click)

        button_list = args.get("button_list", [("Continue", 1, "<Return>")])
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=8, anchor="e")
        _add_buttons(btn_frame, button_list, lambda v: self._close(win, v))
        win.bind("<Escape>", lambda e: self._close(win, None))

        _center_window(win, 900, 500)
        root.wait_window(win)

    def _close(self, win: tk.Toplevel, value: int | None) -> None:
        self.result = {"button": value}
        if win.winfo_exists():
            win.destroy()


# ---------------------------------------------------------------------------
# SelectSubDialog — pick one row, assign column values to vars
# ---------------------------------------------------------------------------


class SelectSubDialog:
    def __init__(self, root: tk.Tk, args: dict) -> None:
        self.result: dict = {}

        win = tk.Toplevel(root)
        win.title(args.get("title", "Select a row"))
        win.grab_set()

        frame = ttk.Frame(win, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        _add_help_button(frame, args.get("help_url"))

        message = args.get("message", "")
        if message:
            ttk.Label(frame, text=message, wraplength=580, anchor="w", justify="left").pack(
                anchor="w",
                pady=(0, 8),
            )

        headers = args.get("headers", [])
        rows = args.get("rows", [])

        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        tree = ttk.Treeview(tree_frame, height=min(10, len(rows)))
        _populate_treeview(tree, headers, rows)
        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Label(frame, text=_row_count_text(len(rows))).pack(anchor="w")

        def _select():
            sel = tree.selection()
            if sel:
                vals = tree.item(sel[0], "values")
                row_dict = dict(zip(headers, vals))
                self.result = {"button": 1, "row": row_dict}
                win.destroy()

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=8, anchor="e")
        ttk.Button(btn_frame, text="OK", command=_select).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel", command=lambda: self._close(win)).pack(side=tk.LEFT, padx=4)
        tree.bind("<Double-1>", lambda e: _select())
        win.bind("<Escape>", lambda e: self._close(win))

        _center_window(win, 600, 350)
        root.wait_window(win)

    def _close(self, win: tk.Toplevel) -> None:
        self.result = {"button": None, "row": None}
        if win.winfo_exists():
            win.destroy()


# ---------------------------------------------------------------------------
# ActionDialog — button grid
# ---------------------------------------------------------------------------


class ActionDialog:
    def __init__(self, root: tk.Tk, args: dict) -> None:
        self.result: dict = {}

        win = tk.Toplevel(root)
        win.title(args.get("title", "Actions"))
        win.grab_set()

        frame = ttk.Frame(win, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        _add_help_button(frame, args.get("help_url"))

        message = args.get("message", "")
        if message:
            ttk.Label(frame, text=message, wraplength=580, anchor="w", justify="left").pack(
                anchor="w",
                pady=(0, 8),
            )

        headers = args.get("column_headers")
        rows = args.get("rowset")
        if headers and rows:
            tree = ttk.Treeview(frame, height=min(6, len(rows)))
            _populate_treeview(tree, headers, rows)
            tree.pack(fill=tk.BOTH, expand=True, pady=(0, 4))
            ttk.Label(frame, text=_row_count_text(len(rows))).pack(anchor="w", pady=(0, 8))

        button_specs = args.get("button_specs", [])
        for i, spec in enumerate(button_specs):
            btn_text = f"{spec.label}\n{spec.prompt}"
            ttk.Button(
                frame,
                text=btn_text,
                command=lambda v=i + 1: self._close(win, v),
            ).pack(fill=tk.X, pady=2)

        include_continue = args.get("include_continue_button")
        if include_continue:
            ttk.Button(frame, text="Continue", command=lambda: self._close(win, 1)).pack(fill=tk.X, pady=2)

        win.bind("<Escape>", lambda e: self._close(win, None))
        _center_window(win, 400, 100 + len(button_specs) * 50)
        root.wait_window(win)

    def _close(self, win: tk.Toplevel, value: int | None) -> None:
        self.result = {"button": value}
        if win.winfo_exists():
            win.destroy()


# ---------------------------------------------------------------------------
# MapDialog — shows tabular data (no interactive map without tkintermapview)
# ---------------------------------------------------------------------------


class MapDialog:
    def __init__(self, root: tk.Tk, args: dict) -> None:
        self.result: dict = {}

        win = tk.Toplevel(root)
        win.title(args.get("title", "Map"))
        win.grab_set()

        frame = ttk.Frame(win, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        message = args.get("message", "")
        if message:
            ttk.Label(frame, text=message, wraplength=580, anchor="w", justify="left").pack(
                anchor="w",
                pady=(0, 4),
            )
        ttk.Label(frame, text="(Interactive map requires tkintermapview; showing tabular data)").pack(
            anchor="w",
            pady=(0, 8),
        )

        headers = args.get("headers", [])
        rows = args.get("rows", [])
        if headers and rows:
            tree_frame = ttk.Frame(frame)
            tree_frame.pack(fill=tk.BOTH, expand=True)
            tree = ttk.Treeview(tree_frame, height=min(12, len(rows)))
            _populate_treeview(tree, headers, rows)
            vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
            tree.configure(yscrollcommand=vsb.set)
            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            vsb.pack(side=tk.RIGHT, fill=tk.Y)
            ttk.Label(frame, text=_row_count_text(len(rows))).pack(anchor="w")

        button_list = args.get("button_list", [("Continue", 1, "<Return>")])
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=8, anchor="e")
        _add_buttons(btn_frame, button_list, lambda v: self._close(win, v))

        _center_window(win, 600, 450)
        root.wait_window(win)

    def _close(self, win: tk.Toplevel, value: int | None) -> None:
        self.result = {"button": value}
        if win.winfo_exists():
            win.destroy()


# ---------------------------------------------------------------------------
# CredentialsDialog
# ---------------------------------------------------------------------------


class CredentialsDialog:
    def __init__(self, root: tk.Tk, args: dict) -> None:
        self.result: dict = {}

        win = tk.Toplevel(root)
        win.title("Credentials")
        win.grab_set()

        frame = ttk.Frame(win, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        _add_help_button(frame, args.get("help_url"))

        message = args.get("message", "")
        if message:
            ttk.Label(frame, text=message, wraplength=380, anchor="w", justify="left").pack(
                anchor="w",
                pady=(0, 8),
            )

        user_var = tk.StringVar()
        pw_var = tk.StringVar()

        ttk.Label(frame, text="Username:").grid(row=0, column=0, sticky="e", padx=4, pady=4)
        ttk.Entry(frame, textvariable=user_var, width=30).grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Password:").grid(row=1, column=0, sticky="e", padx=4, pady=4)
        ttk.Entry(frame, textvariable=pw_var, show="*", width=30).grid(row=1, column=1, sticky="ew", pady=4)
        frame.columnconfigure(1, weight=1)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=8, sticky="e")
        ttk.Button(btn_frame, text="OK", command=lambda: self._close(win, user_var.get(), pw_var.get())).pack(
            side=tk.LEFT,
            padx=4,
        )
        ttk.Button(btn_frame, text="Cancel", command=lambda: self._close(win, "", "")).pack(side=tk.LEFT, padx=4)
        win.bind("<Return>", lambda e: self._close(win, user_var.get(), pw_var.get()))
        win.bind("<Escape>", lambda e: self._close(win, "", ""))

        _center_window(win, 380, 180)
        root.wait_window(win)

    def _close(self, win: tk.Toplevel, username: str, password: str) -> None:
        self.result = {"username": username, "password": password}
        if win.winfo_exists():
            win.destroy()


# ---------------------------------------------------------------------------
# ConnectDialog
# ---------------------------------------------------------------------------

_DB_TYPE_OPTIONS = [
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


class ConnectDialog:
    def __init__(self, root: tk.Tk, args: dict) -> None:
        self.result: dict = {}

        win = tk.Toplevel(root)
        win.title("Connect to Database")
        win.grab_set()

        frame = ttk.Frame(win, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        _add_help_button(frame, args.get("help_url"))

        message = args.get("message", "")
        if message:
            ttk.Label(frame, text=message, wraplength=480, anchor="w", justify="left").pack(
                anchor="w",
                pady=(0, 8),
            )

        type_var = tk.StringVar(value="p")
        server_var = tk.StringVar()
        db_var = tk.StringVar()
        user_var = tk.StringVar()

        def _make_row(parent, row, label, widget_factory):
            ttk.Label(parent, text=label, anchor="e").grid(row=row, column=0, sticky="e", padx=4, pady=4)
            w = widget_factory(parent)
            w.grid(row=row, column=1, sticky="ew", pady=4)
            return w

        form = ttk.Frame(frame)
        form.pack(fill=tk.BOTH, expand=True)
        form.columnconfigure(1, weight=1)

        type_labels = [f"{k} — {v}" for k, v in _DB_TYPE_OPTIONS]
        type_values = [k for k, v in _DB_TYPE_OPTIONS]
        type_combo = ttk.Combobox(form, textvariable=type_var, values=type_labels, state="readonly", width=30)
        type_combo.current(0)
        type_var.trace_add("write", lambda *a: None)  # placeholder
        _make_row(form, 0, "Database type:", lambda p: type_combo)
        ttk.Label(form, text="Server:").grid(row=1, column=0, sticky="e", padx=4, pady=4)
        ttk.Entry(form, textvariable=server_var, width=35).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="Database/File:").grid(row=2, column=0, sticky="e", padx=4, pady=4)
        ttk.Entry(form, textvariable=db_var, width=35).grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="Username:").grid(row=3, column=0, sticky="e", padx=4, pady=4)
        ttk.Entry(form, textvariable=user_var, width=35).grid(row=3, column=1, sticky="ew", pady=4)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=8, anchor="e")

        def _on_connect():
            idx = type_combo.current()
            db_type = type_values[idx] if idx >= 0 else "p"
            db = db_var.get().strip() or None
            self.result = {
                "db_type": db_type,
                "server": server_var.get().strip() or None,
                "database": db,
                "db_file": db if db_type in ("l", "k", "a") else None,
                "username": user_var.get().strip() or None,
            }
            win.destroy()

        ttk.Button(btn_frame, text="Connect", command=_on_connect).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel", command=lambda: self._close(win)).pack(side=tk.LEFT, padx=4)
        win.bind("<Return>", lambda e: _on_connect())
        win.bind("<Escape>", lambda e: self._close(win))

        _center_window(win, 440, 240)
        root.wait_window(win)

    def _close(self, win: tk.Toplevel) -> None:
        self.result = {"db_type": None}
        if win.winfo_exists():
            win.destroy()


# ---------------------------------------------------------------------------
# ConsoleWindow — floating text output window
# ---------------------------------------------------------------------------


class ConsoleWindow:
    """Persistent console window for WRITE metacommand output."""

    def __init__(self, root: tk.Tk, width: int = 100, height: int = 25) -> None:
        self._root = root
        self._running = False
        self._win: tk.Toplevel | None = None
        self._text: scrolledtext.ScrolledText | None = None
        self._status_var: tk.StringVar | None = None
        self._progress_var: tk.DoubleVar | None = None
        self._progress_bar: ttk.Progressbar | None = None
        self._width = width
        self._height = height

    def start(self) -> None:
        if self._running:
            return
        self._win = tk.Toplevel(self._root)
        self._win.title("execsql Console")
        self._win.protocol("WM_DELETE_WINDOW", self._on_close)

        frame = ttk.Frame(self._win)
        frame.pack(fill=tk.BOTH, expand=True)

        self._text = scrolledtext.ScrolledText(
            frame,
            width=self._width,
            height=self._height,
            font=_CONSOLE_FONT,
            state=tk.DISABLED,
        )
        self._text.pack(fill=tk.BOTH, expand=True)

        # Progress bar + status bar at the bottom
        bottom_frame = ttk.Frame(self._win)
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self._progress_var = tk.DoubleVar(value=0.0)
        self._progress_bar = ttk.Progressbar(
            bottom_frame,
            variable=self._progress_var,
            maximum=100,
            length=120,
            mode="determinate",
        )
        self._progress_bar.pack(side=tk.RIGHT, padx=4, pady=2)

        self._status_var = tk.StringVar(value="Ready")
        ttk.Label(bottom_frame, textvariable=self._status_var, anchor="w").pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
            padx=4,
        )

        self._running = True
        _center_window(self._win, self._width * 8, self._height * 20)

    def _on_close(self) -> None:
        self._running = False
        if self._win and self._win.winfo_exists():
            self._win.destroy()
        self._win = None
        self._text = None
        self._progress_var = None
        self._progress_bar = None
        try:
            import execsql.state as _state

            if _state.output is not None and _state.output.write_func is self.write:
                _state.output.reset()
        except Exception:
            pass  # Best-effort output reset during console teardown.

    def write(self, text: str) -> None:
        if self._text and self._text.winfo_exists():
            self._text.configure(state=tk.NORMAL)
            self._text.insert(tk.END, text)
            self._text.see(tk.END)
            self._text.configure(state=tk.DISABLED)
            if self._win and self._win.winfo_exists():
                self._win.update_idletasks()

    def set_status(self, message: str) -> None:
        if self._status_var:
            self._status_var.set(message)

    def set_progress(self, pct: float) -> None:
        """Update the progress bar (0–100)."""
        if self._progress_var is not None:
            self._progress_var.set(max(0.0, min(100.0, pct)))

    def save(self, outfile: str, append: bool = False) -> None:
        """Save the console text contents to *outfile*."""
        if self._text is None:
            return
        contents = self._text.get("1.0", tk.END)
        mode = "a" if append else "w"
        with open(outfile, mode, encoding="utf-8") as fh:
            fh.write(contents)

    def stop(self) -> None:
        self._on_close()

    def is_running(self) -> bool:
        return self._running


# ---------------------------------------------------------------------------
# TkinterBackend — the main backend class
# ---------------------------------------------------------------------------


class TkinterBackend(GuiBackend):
    """GUI backend using Python's built-in tkinter. Requires a display server."""

    def __init__(self) -> None:
        self._root: tk.Tk | None = None
        self._console: ConsoleWindow | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Create the hidden root Tk window."""
        if self._root is not None:
            return
        self._root = tk.Tk()
        self._root.withdraw()  # hide the root window — we only show dialog children

    def stop(self) -> None:
        if self._console:
            self._console.stop()
        if self._root:
            try:
                self._root.destroy()
            except Exception:
                pass  # Tk root may already be destroyed.
            self._root = None

    def _root_or_raise(self) -> tk.Tk:
        if self._root is None:
            self.start()
        assert self._root is not None
        return self._root

    # ------------------------------------------------------------------
    # Console lifecycle
    # ------------------------------------------------------------------

    def console_on(self) -> None:
        root = self._root_or_raise()
        if self._console is None:
            self._console = ConsoleWindow(root)
        self._console.start()
        import execsql.state as _state

        _state.output.redir_stdout(self._console.write)
        _state.output.redir_stderr(self._console.write)

    def console_off(self) -> None:
        if self._console:
            self._console.stop()
            self._console = None
        import execsql.state as _state

        if _state.output is not None:
            _state.output.reset()

    def console_hide(self) -> None:
        if self._console and self._console._win:
            self._console._win.withdraw()

    def console_show(self) -> None:
        if self._console and self._console._win:
            self._console._win.deiconify()

    def console_status(self, message: str) -> None:
        if self._console:
            self._console.set_status(message)

    def console_progress(self, num: float, total: float | None = None) -> None:
        """Update the console progress bar (0–100, or num/total if total provided)."""
        if self._console:
            pct = (num / total * 100.0) if total else num
            self._console.set_progress(pct)

    def console_save(self, outfile: str, append: bool = False) -> None:
        """Save console text contents to *outfile*."""
        if self._console:
            self._console.save(outfile, append)

    def console_wait_user(self, message: str = "") -> None:
        """Block until the user closes the console window."""
        if self._console:
            while self._console.is_running():
                if self._root:
                    try:
                        self._root.update()
                    except Exception:
                        break
                time.sleep(0.05)

    def query_console(self, args: dict) -> dict:
        return {"console_running": self._console is not None and self._console.is_running()}

    # ------------------------------------------------------------------
    # Dialog dispatchers
    # ------------------------------------------------------------------

    def _run_dialog(self, dialog_class, args: dict) -> dict:
        root = self._root_or_raise()
        dlg = dialog_class(root, args)
        root.update()
        return dlg.result

    def show_halt(self, args: dict) -> dict:
        return self._run_dialog(MsgDialog, args)

    def show_msg(self, args: dict) -> dict:
        return self._run_dialog(MsgDialog, args)

    def show_pause(self, args: dict) -> dict:
        return self._run_dialog(PauseDialog, args)

    def show_display(self, args: dict) -> dict:
        return self._run_dialog(DisplayDialog, args)

    def show_entry_form(self, args: dict) -> dict:
        return self._run_dialog(EntryFormDialog, args)

    def show_compare(self, args: dict) -> dict:
        return self._run_dialog(CompareDialog, args)

    def show_select_rows(self, args: dict) -> dict:
        return self._run_dialog(SelectRowsDialog, args)

    def show_select_sub(self, args: dict) -> dict:
        return self._run_dialog(SelectSubDialog, args)

    def show_action(self, args: dict) -> dict:
        return self._run_dialog(ActionDialog, args)

    def show_map(self, args: dict) -> dict:
        return self._run_dialog(MapDialog, args)

    def show_open_file(self, args: dict) -> dict:
        root = self._root_or_raise()
        working_dir = args.get("working_dir", os.getcwd())
        fn = filedialog.askopenfilename(parent=root, initialdir=working_dir)
        return {"filename": fn or None}

    def show_save_file(self, args: dict) -> dict:
        root = self._root_or_raise()
        working_dir = args.get("working_dir", os.getcwd())
        fn = filedialog.asksaveasfilename(parent=root, initialdir=working_dir)
        return {"filename": fn or None}

    def show_directory(self, args: dict) -> dict:
        root = self._root_or_raise()
        working_dir = args.get("working_dir", os.getcwd())
        dn = filedialog.askdirectory(parent=root, initialdir=working_dir)
        return {"directory": dn or None}

    def show_credentials(self, args: dict) -> dict:
        return self._run_dialog(CredentialsDialog, args)

    def show_connect(self, args: dict) -> dict:
        return self._run_dialog(ConnectDialog, args)


# ---------------------------------------------------------------------------
# _TkinterSyncQueue — synchronous gui_manager_queue replacement for level 3
# ---------------------------------------------------------------------------


class _TkinterSyncQueue:
    """Drop-in replacement for ``_state.gui_manager_queue`` on the Tkinter path.

    gui_level == 3 with tkinter available: instead of a background manager
    thread, ``put()`` dispatches the dialog synchronously in the calling
    (main) thread.  After ``put()`` returns, the result is already on
    ``spec.return_queue`` so the calling metacommand's ``get()`` unblocks
    immediately.

    Tkinter requires all widget operations to run on the main thread
    (mandatory on macOS, strongly recommended everywhere).
    """

    import queue as _stdlib_queue

    def __init__(self, backend: TkinterBackend) -> None:
        self._backend = backend

    # GUI types for which a None/cancelled result means the user wants to exit.
    # File/directory/credentials/connect dialogs are intentionally excluded
    # because cancelling those just means "no selection" rather than "quit".
    _EXIT_ON_CANCEL = frozenset(
        [
            "halt",
            "msg",
            "pause",
            "display",
            "entry",
            "compare",
            "selectrows",
            "selectsub",
            "action",
            "map",
        ],
    )

    def put(self, spec: Any, block: bool = True, timeout: Any = None) -> None:
        if spec is None:
            return
        from execsql.utils.gui import QUERY_CONSOLE

        if spec.gui_type == QUERY_CONSOLE:
            spec.return_queue.put(self._backend.query_console({}))
            return
        try:
            result = self._backend.dispatch(spec)
            # Keep the Tk event loop alive so the console window stays responsive.
            if self._backend._root:
                try:
                    self._backend._root.update()
                except Exception:
                    pass  # Tk event loop may be torn down.
        except Exception as exc:
            result = {"error": str(exc), "button": None}
        if result is not None and spec.gui_type in self._EXIT_ON_CANCEL and result.get("button") is None:
            raise SystemExit(2)
        spec.return_queue.put(result if result is not None else {})

    def get_nowait(self) -> Any:
        import queue as _q

        raise _q.Empty

    def get(self, block: bool = True, timeout: Any = None) -> Any:
        import queue as _q

        raise _q.Empty
