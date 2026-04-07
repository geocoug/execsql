"""Console (terminal) fallback GUI backend for execsql.

Implements all dialog types using stdin/stdout so execsql can run
fully headless over SSH or in any environment without a display.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any

from execsql.gui.base import GuiBackend, compare_stats as _compare_stats

__all__ = ["ConsoleBackend"]


def _print_help_url(args: dict) -> None:
    """Print the help URL if present in *args*."""
    url = args.get("help_url")
    if url:
        print(f"  Help: {url}", file=sys.stderr)


def _row_count_text(n: int) -> str:
    """Return a human-readable row count string, e.g. '3 rows' or '1 row'."""
    return f"{n:,} row{'s' if n != 1 else ''}"


def _print_table(headers: list, rows: list, file: Any = None) -> None:
    """Print a simple ASCII table to the given file (default stderr)."""
    if file is None:
        file = sys.stderr
    if not headers:
        return
    col_widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell) if cell is not None else ""))
    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in col_widths)
    sep = "  " + "  ".join("-" * w for w in col_widths)
    print(fmt.format(*[str(h) for h in headers]), file=file)
    print(sep, file=file)
    for row in rows:
        print(fmt.format(*[str(c) if c is not None else "" for c in row]), file=file)


def _prompt_buttons(button_list: list) -> int | None:
    """Present a list of buttons as numbered choices; return chosen value or None."""
    if not button_list:
        input("Press Enter to continue...")
        return 1
    choices = {}
    parts = []
    for i, btn in enumerate(button_list, 1):
        label = btn[0]
        value = btn[1]
        choices[str(i)] = value
        choices[label.lower()] = value
        parts.append(f"[{i}] {label}")
    print("  " + "  ".join(parts), file=sys.stderr)
    while True:
        raw = input("Choice: ").strip()
        if raw.lower() in choices:
            return choices[raw.lower()]
        if raw in choices:
            return choices[raw]
        print("Invalid choice, please try again.", file=sys.stderr)


class ConsoleBackend(GuiBackend):
    """Terminal-only backend. Uses input()/print() for all interactions."""

    def __init__(self) -> None:
        self._console_running = False

    # ------------------------------------------------------------------
    # Console lifecycle (override of base no-ops)
    # ------------------------------------------------------------------

    def console_on(self) -> None:
        self._console_running = True

    def console_off(self) -> None:
        self._console_running = False

    def console_wait_user(self, message: str = "") -> None:
        if message:
            print(message, file=sys.stderr)

    # ------------------------------------------------------------------
    # Dialog implementations
    # ------------------------------------------------------------------

    def show_halt(self, args: dict) -> dict:
        title = args.get("title", "HALT")
        message = args.get("message", "")
        print(f"\n[{title}] {message}", file=sys.stderr)
        headers = args.get("column_headers")
        rows = args.get("rowset")
        if headers and rows:
            _print_table(headers, rows)
            print(f"  {_row_count_text(len(rows))}", file=sys.stderr)
        input("Press Enter to acknowledge...")
        return {"button": 1}

    def show_msg(self, args: dict) -> dict:
        title = args.get("title", "Message")
        message = args.get("message", "")
        print(f"\n[{title}] {message}", file=sys.stderr)
        input("Press Enter to close...")
        return {"button": 1}

    def show_pause(self, args: dict) -> dict:
        message = args.get("message", "")
        countdown = args.get("countdown")
        print(f"\n{message}", file=sys.stderr)
        if countdown is not None:
            print(f"(Auto-continuing in {countdown:.0f} seconds...)", file=sys.stderr)
            time.sleep(float(countdown))
            return {"quit": False}
        raw = input("Press Enter to continue, or 'q' to cancel: ").strip().lower()
        return {"quit": raw == "q"}

    def show_display(self, args: dict) -> dict:
        title = args.get("title", "")
        message = args.get("message", "")
        headers = args.get("column_headers")
        rows = args.get("rowset")
        button_list = args.get("button_list", [("Continue", 1, "<Return>")])
        textentry = args.get("textentry", False)
        hidetext = args.get("hidetext", False)
        initial = args.get("initialtext", "")
        if title:
            print(f"\n=== {title} ===", file=sys.stderr)
        if message:
            print(message, file=sys.stderr)
        _print_help_url(args)
        if headers and rows:
            _print_table(headers, rows)
            print(f"  {_row_count_text(len(rows))}", file=sys.stderr)

        return_value = None
        if textentry:
            if hidetext:
                import getpass

                return_value = getpass.getpass("Enter value: ")
            else:
                return_value = input(f"Enter value [{initial}]: ").strip() or initial

        btn = _prompt_buttons(button_list)
        return {"button": btn, "return_value": return_value}

    def show_entry_form(self, args: dict) -> dict:
        title = args.get("title", "Entry")
        message = args.get("message", "")
        entry_specs = args.get("entry_specs", [])
        headers = args.get("column_headers")
        rows = args.get("rowset")

        if title:
            print(f"\n=== {title} ===", file=sys.stderr)
        if message:
            print(message, file=sys.stderr)
        _print_help_url(args)
        if headers and rows:
            _print_table(headers, rows)
            print(f"  {_row_count_text(len(rows))}", file=sys.stderr)

        for spec in entry_specs:
            entry_type = (spec.entry_type or "text").lower()
            initial = spec.initial_value or ""
            if entry_type == "checkbox":
                raw = input(f"{spec.label} [y/n, current={initial}]: ").strip().lower()
                spec.value = "1" if raw in ("y", "yes", "true", "1") else "0"
            elif entry_type in ("dropdown", "select") and spec.lookup_list:
                choices = spec.lookup_list
                print(f"{spec.label}:", file=sys.stderr)
                for i, c in enumerate(choices, 1):
                    print(f"  [{i}] {c}", file=sys.stderr)
                while True:
                    raw = input("Choice number or value: ").strip()
                    if raw.isdigit() and 1 <= int(raw) <= len(choices):
                        spec.value = choices[int(raw) - 1]
                        break
                    if raw in choices:
                        spec.value = raw
                        break
                    print("Invalid choice.", file=sys.stderr)
            elif entry_type == "listbox" and spec.lookup_list:
                choices = spec.lookup_list
                print(f"{spec.label} (enter numbers separated by commas):", file=sys.stderr)
                for i, c in enumerate(choices, 1):
                    print(f"  [{i}] {c}", file=sys.stderr)
                raw = input("Selections: ").strip()
                selected = []
                for part in raw.split(","):
                    part = part.strip()
                    if part.isdigit() and 1 <= int(part) <= len(choices):
                        selected.append(choices[int(part) - 1])
                spec.value = ",".join(f"'{v.replace(chr(39), chr(39) + chr(39))}'" for v in selected)
            elif entry_type == "radiobuttons":
                parts = (spec.label or "").split(";")
                label = parts[0] if parts else spec.label
                buttons = parts[1:] if len(parts) > 1 else [spec.label or "Option"]
                print(f"{label}:", file=sys.stderr)
                for i, b in enumerate(buttons, 1):
                    print(f"  [{i}] {b.strip()}", file=sys.stderr)
                while True:
                    raw = input("Choice number: ").strip()
                    if raw.isdigit() and 1 <= int(raw) <= len(buttons):
                        spec.value = raw
                        break
                    print("Invalid choice.", file=sys.stderr)
            elif entry_type == "textarea":
                print(f"{spec.label} (enter text, blank line to finish):", file=sys.stderr)
                lines = []
                while True:
                    line = input()
                    if not line:
                        break
                    lines.append(line)
                spec.value = "\n".join(lines) or initial
            elif entry_type in ("inputfile", "outputfile"):
                raw = input(f"{spec.label} (file path) [{initial}]: ").strip()
                spec.value = raw or initial
            else:
                raw = input(f"{spec.label} [{initial}]: ").strip()
                spec.value = raw or initial

        print("", file=sys.stderr)
        raw = input("Submit? [y/n]: ").strip().lower()
        if raw in ("y", "yes", ""):
            return {"button": 1, "return_value": entry_specs}
        return {"button": None, "return_value": entry_specs}

    def show_compare(self, args: dict) -> dict:
        title = args.get("title", "Compare")
        message = args.get("message", "")
        headers1 = args.get("headers1", [])
        rows1 = args.get("rows1", [])
        headers2 = args.get("headers2", [])
        rows2 = args.get("rows2", [])
        button_list = args.get("button_list", [("Continue", 1, "<Return>")])

        print(f"\n=== {title} ===", file=sys.stderr)
        if message:
            print(message, file=sys.stderr)
        _print_help_url(args)
        print("\n--- Table 1 ---", file=sys.stderr)
        _print_table(headers1, rows1)
        print(f"  {_row_count_text(len(rows1))}", file=sys.stderr)
        print("\n--- Table 2 ---", file=sys.stderr)
        _print_table(headers2, rows2)
        print(f"  {_row_count_text(len(rows2))}", file=sys.stderr)

        keylist = [str(k) for k in args.get("keylist", [])]
        summary = _compare_stats(headers1, rows1, headers2, rows2, keylist)
        if summary:
            print(f"\n  {summary}", file=sys.stderr)

        btn = _prompt_buttons(button_list)
        return {"button": btn}

    def show_select_rows(self, args: dict) -> dict:
        title = args.get("title", "Select rows")
        message = args.get("message", "")
        headers1 = args.get("headers1", [])
        rows1 = args.get("rows1", [])
        button_list = args.get("button_list", [("Continue", 1, "<Return>")])

        print(f"\n=== {title} ===", file=sys.stderr)
        if message:
            print(message, file=sys.stderr)
        _print_help_url(args)
        _print_table(headers1, rows1)
        print(f"  {_row_count_text(len(rows1))}", file=sys.stderr)
        print("(Row selection requires a GUI backend; displaying source data only.)", file=sys.stderr)

        btn = _prompt_buttons(button_list)
        return {"button": btn}

    def show_select_sub(self, args: dict) -> dict:
        title = args.get("title", "Select a row")
        message = args.get("message", "")
        headers = args.get("headers", [])
        rows = args.get("rows", [])

        print(f"\n=== {title} ===", file=sys.stderr)
        if message:
            print(message, file=sys.stderr)
        if headers and rows:
            for i, row in enumerate(rows, 1):
                print(f"  [{i}] " + ", ".join(f"{h}={v}" for h, v in zip(headers, row)), file=sys.stderr)
            while True:
                raw = input("Select row number (or blank to cancel): ").strip()
                if not raw:
                    return {"button": None, "row": None}
                if raw.isdigit() and 1 <= int(raw) <= len(rows):
                    row = dict(zip(headers, rows[int(raw) - 1]))
                    return {"button": 1, "row": row}
                print("Invalid selection.", file=sys.stderr)
        return {"button": None, "row": None}

    def show_action(self, args: dict) -> dict:
        title = args.get("title", "Actions")
        message = args.get("message", "")
        button_specs = args.get("button_specs", [])
        headers = args.get("column_headers")
        rows = args.get("rowset")

        print(f"\n=== {title} ===", file=sys.stderr)
        if message:
            print(message, file=sys.stderr)
        _print_help_url(args)
        if headers and rows:
            _print_table(headers, rows)
            print(f"  {_row_count_text(len(rows))}", file=sys.stderr)

        if not button_specs:
            input("Press Enter to continue...")
            return {"button": 1}

        print("\nAvailable actions:", file=sys.stderr)
        for i, spec in enumerate(button_specs, 1):
            print(f"  [{i}] {spec.label} — {spec.prompt}", file=sys.stderr)

        include_continue = args.get("include_continue_button")
        if include_continue:
            print("  [0] Continue", file=sys.stderr)

        while True:
            raw = input("Select action: ").strip()
            if include_continue and raw == "0":
                return {"button": 1}
            if raw.isdigit() and 1 <= int(raw) <= len(button_specs):
                return {"button": int(raw)}
            print("Invalid choice.", file=sys.stderr)

    def show_map(self, args: dict) -> dict:
        title = args.get("title", "Map")
        message = args.get("message", "")
        headers = args.get("headers", [])
        rows = args.get("rows", [])
        lat_col = args.get("lat_col")
        lon_col = args.get("lon_col")
        label_col = args.get("label_col")
        button_list = args.get("button_list", [("Continue", 1, "<Return>")])

        print(f"\n=== {title} ===", file=sys.stderr)
        if message:
            print(message, file=sys.stderr)
        print("(Interactive map requires a GUI backend; showing tabular data.)", file=sys.stderr)
        _print_table(headers, rows)
        if rows:
            print(f"  {_row_count_text(len(rows))}", file=sys.stderr)

        if lat_col and lon_col and headers and rows:
            try:
                lat_i = headers.index(lat_col)
                lon_i = headers.index(lon_col)
                label_i = headers.index(label_col) if label_col and label_col in headers else None
                print("\nLocations:", file=sys.stderr)
                for row in rows:
                    label = row[label_i] if label_i is not None else ""
                    print(f"  {label}  lat={row[lat_i]}  lon={row[lon_i]}", file=sys.stderr)
            except (ValueError, IndexError):
                pass

        btn = _prompt_buttons(button_list)
        return {"button": btn}

    def show_open_file(self, args: dict) -> dict:
        working_dir = args.get("working_dir", os.getcwd())
        print(f"\nOpen file (starting in: {working_dir})", file=sys.stderr)
        fn = input("File path (or blank to cancel): ").strip()
        return {"filename": fn or None}

    def show_save_file(self, args: dict) -> dict:
        working_dir = args.get("working_dir", os.getcwd())
        print(f"\nSave file (starting in: {working_dir})", file=sys.stderr)
        fn = input("File path (or blank to cancel): ").strip()
        return {"filename": fn or None}

    def show_directory(self, args: dict) -> dict:
        working_dir = args.get("working_dir", os.getcwd())
        print(f"\nSelect directory (starting in: {working_dir})", file=sys.stderr)
        dn = input("Directory path (or blank to cancel): ").strip()
        return {"directory": dn or None}

    def query_console(self, args: dict) -> dict:
        return {"console_running": self._console_running}

    def show_credentials(self, args: dict) -> dict:
        message = args.get("message", "")
        if message:
            print(message, file=sys.stderr)
        _print_help_url(args)
        username = input("Username: ").strip()
        import getpass

        password = getpass.getpass(f"Password for {username}: ")
        return {"username": username, "password": password}

    def show_connect(self, args: dict) -> dict:
        message = args.get("message", "")
        if message:
            print(message, file=sys.stderr)
        _print_help_url(args)
        db_types = {
            "p": "PostgreSQL",
            "s": "SQL Server",
            "l": "SQLite",
            "m": "MySQL/MariaDB",
            "k": "DuckDB",
            "o": "Oracle",
            "f": "Firebird",
            "a": "MS-Access",
            "d": "DSN",
        }
        print("Database types:", file=sys.stderr)
        for k, v in db_types.items():
            print(f"  {k} — {v}", file=sys.stderr)
        db_type = input("Database type: ").strip().lower()
        server = input("Server (or blank): ").strip() or None
        database = input("Database (or blank): ").strip() or None
        db_file = input("File path (or blank): ").strip() or None
        username = input("Username (or blank): ").strip() or None
        return {
            "db_type": db_type,
            "server": server,
            "database": database,
            "db_file": db_file,
            "username": username,
        }
