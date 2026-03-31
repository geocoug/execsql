"""Rich-formatted help output for the execsql CLI.

Contains the metacommand reference table, encoding list, and the shared
``Console`` instances used by the other CLI submodules.
"""

from __future__ import annotations

from encodings.aliases import aliases as codec_dict

from rich.console import Console
from rich.table import Table

__all__ = ["_console", "_err_console", "_print_encodings", "_print_metacommands"]

_console = Console()
_err_console = Console(stderr=True)

# ---------------------------------------------------------------------------
# Metacommand syntax hints — paired with keywords from the dispatch table.
# Keys must match the ``description`` values used in mcl.add() calls.
# Entries here are validated by tests/test_registry.py.
# ---------------------------------------------------------------------------

_SYNTAX: dict[str, tuple[str, str]] = {
    # (display_name, syntax_hint)
    "ASK": ("ASK", '"<question>" SUB <match_string>'),
    "AUTOCOMMIT": ("AUTOCOMMIT", "ON|OFF"),
    "BEGIN BATCH": ("BEGIN BATCH / END BATCH / ROLLBACK BATCH", ""),
    "BEGIN SCRIPT": ("BEGIN SCRIPT / END SCRIPT", ""),
    "BEGIN SQL": ("BEGIN SQL / END SQL", ""),
    "CANCEL_HALT": ("CANCEL_HALT", "ON|OFF"),
    "CD": ("CD", "<directory>"),
    "CONNECT": ("CONNECT", "<alias> [AS <alias_name>]"),
    "COPY": ("COPY", "<source_file> TO <dest_file>"),
    "DEBUG": ("DEBUG", "ON|OFF"),
    "SUB": ("DEFINE SUB", "<variable> [AS] <value>"),
    "EXPORT QUERY": ("EXPORT QUERY", "<queryname> [AS <alias>] ..."),
    "EXPORT": ("EXPORT", "<queryname> TO <format> <filename> ..."),
    "HALT": ("HALT [ON]", "ERROR|CANCEL"),
    "IF": ("IF <condition>", "/ ELSE / ENDIF"),
    "IMPORT_FILE": ("IMPORT FILE", "<filename> [OPTIONS ...]"),
    "IMPORT": ("IMPORT TABLE", "<tablename> FROM FILE <filename> [OPTIONS ...]"),
    "LOOP": ("LOOP <n> TIMES | WHILE | UNTIL", "/ END LOOP"),
    "CONFIG": ("CONFIG", "<option> <value>"),
    "ON CANCEL_HALT": ("ON CANCEL_HALT", "..."),
    "ON ERROR_HALT": ("ON ERROR_HALT", "..."),
    "PAUSE": ("PAUSE", "[<text>]"),
    "PROMPT ACTION": ("PROMPT ACTION", "..."),
    "PROMPT ENTRY_FORM": ("PROMPT ENTRY_FORM", "..."),
    "PROMPT OPENFILE": ("PROMPT OPENFILE", "..."),
    "PROMPT SAVEFILE": ("PROMPT SAVEFILE", "..."),
    "PROMPT DIRECTORY": ("PROMPT DIRECTORY", "..."),
    "PROMPT MAP": ("PROMPT MAP", "..."),
    "ROLLBACK BATCH": ("ROLLBACK", ""),
    "SERVE": ("SERVE", "<queryname> ..."),
    "SYSTEM_CMD": ("SYSTEM_CMD", "(<operating system command line>)"),
    "TIMER": ("TIMER", "ON|OFF"),
    "USE": ("USE", "<alias_name>"),
    "WAIT_UNTIL": ("WAIT_UNTIL", "<Boolean_expression> <HALT|CONTINUE> AFTER <n> SECONDS"),
    "WRITE": ("WRITE", '"<text>" [[TEE] TO <output>]'),
    "WRITE CREATE_TABLE": ("WRITE CREATE_TABLE FROM", "<filename> [TO <output>]"),
    "WRITE SCRIPT": ("WRITE SCRIPT", "<script_name> [[APPEND] TO <output_file>]"),
    "ZIP": ("ZIP", "<filename> [APPEND] TO ZIPFILE <zipfilename>"),
    "SUB_TEMPFILE": ("SUB_TEMPFILE", "<variable>"),
}

# Keys from _SYNTAX that should be skipped when auto-generating from dispatch
# table (they're variants covered by another entry).
_SKIP_FROM_DISPATCH = {
    "END BATCH",
    "END SCRIPT",
    "END SQL",
    "ROLLBACK BATCH",
    "BEGIN SCRIPT",
    "BEGIN SQL",
}


def _print_metacommands() -> None:
    """Print the metacommands table using Rich.

    Keyword list is derived from the dispatch table; syntax hints come from
    the ``_SYNTAX`` dict above.  Keywords not in ``_SYNTAX`` are shown without
    a syntax column.
    """
    from execsql.metacommands import DISPATCH_TABLE

    table = Table(
        title="execsql Metacommands",
        caption="Embed in SQL comment lines following the [bold]!x![/bold] token.",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        expand=False,
    )
    table.add_column("Metacommand", style="bold green", no_wrap=True)
    table.add_column("Syntax", style="white")

    # Collect unique keyword names from the dispatch table.
    seen: set[str] = set()
    keywords: list[str] = []
    for mc in DISPATCH_TABLE:
        if mc.description and mc.description not in seen and mc.description not in _SKIP_FROM_DISPATCH:
            seen.add(mc.description)
            keywords.append(mc.description)
    # Add parser-level keywords not in the dispatch table.
    for extra in ("BEGIN BATCH", "BEGIN SCRIPT", "BEGIN SQL"):
        if extra not in seen:
            seen.add(extra)
            keywords.append(extra)

    for kw in sorted(keywords):
        if kw in _SYNTAX:
            name, syntax = _SYNTAX[kw]
            table.add_row(name, syntax)
        elif kw.startswith("CONFIG ") or kw.startswith("CONSOLE_") or "_" in kw:
            continue  # skip config options / internal entries
        else:
            table.add_row(kw, "")

    _console.print(table)


def _print_encodings() -> None:
    """Print available encodings using Rich."""
    enc = sorted(codec_dict.keys())
    table = Table(
        title="Available Encodings",
        show_header=False,
        border_style="dim",
        expand=True,
    )
    table.add_column("Encoding", style="cyan")
    # 4 columns
    cols = 4
    for i in range(0, len(enc), cols):
        row = enc[i : i + cols]
        while len(row) < cols:
            row.append("")
        table.add_row(*row)
    _console.print(table)
