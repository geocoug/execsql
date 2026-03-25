"""Rich-formatted help output for the execsql CLI.

Contains the metacommand reference table, encoding list, and the shared
``Console`` instances used by the other ``_cli_*`` modules.
"""

from __future__ import annotations

from encodings.aliases import aliases as codec_dict

from rich.console import Console
from rich.table import Table

_console = Console()
_err_console = Console(stderr=True)

# ---------------------------------------------------------------------------
# Metacommand help text
# ---------------------------------------------------------------------------

_METACOMMANDS = [
    ("ASK", '"<question>" SUB <match_string>'),
    ("AUTOCOMMIT", "ON|OFF"),
    ("BEGIN BATCH / END BATCH / ROLLBACK BATCH", ""),
    ("BEGIN SCRIPT / END SCRIPT", ""),
    ("BEGIN SQL / END SQL", ""),
    ("CANCEL_HALT", "ON|OFF"),
    ("CD", "<directory>"),
    ("CONNECT", "<alias> [AS <alias_name>]"),
    ("COPY", "<source_file> TO <dest_file>"),
    ("DEBUG", "ON|OFF"),
    ("DEFINE SUB", "<variable> [AS] <value>"),
    ("EXPORT QUERY", "<queryname> [AS <alias>] ..."),
    ("EXPORT", "<queryname> TO <format> <filename> ..."),
    ("HALT [ON]", "ERROR|CANCEL"),
    ("IF <condition>", "/ ELSE / ENDIF"),
    ("IMPORT FILE", "<filename> [OPTIONS ...]"),
    ("IMPORT TABLE", "<tablename> FROM FILE <filename> [OPTIONS ...]"),
    ("LOOP <n> TIMES", "/ END LOOP"),
    ("LOOP WHILE <condition>", "/ END LOOP"),
    ("LOOP UNTIL <condition>", "/ END LOOP"),
    ("ON CANCEL_HALT", "..."),
    ("ON ERROR_HALT", "..."),
    ("PAUSE", "[<text>]"),
    ("PROMPT ACTION", "..."),
    ("PROMPT ENTRY_FORM", "..."),
    ("PROMPT MENU", "..."),
    ("PROMPT OPENFILE", "..."),
    ("PROMPT SAVEFILE", "..."),
    ("PROMPT DIRECTORY", "..."),
    ("PROMPT MAP", "..."),
    ("RECONNECT", ""),
    ("ROLLBACK", ""),
    ("SERVE", "<queryname> ..."),
    ("SET AUTOCOMMIT", "ON|OFF"),
    ("SHELL", "(<command>)"),
    ("SHOW WARNINGS", "ON|OFF"),
    ("SUB", "<variable> [AS] <value>"),
    ("SUB_TEMPFILE", "<variable>"),
    ("SYSTEM_CMD", "(<operating system command line>)"),
    ("TIMER", "ON|OFF"),
    ("USE", "<alias_name>"),
    ("WAIT_UNTIL", "<Boolean_expression> <HALT|CONTINUE> AFTER <n> SECONDS"),
    ("WRITE", '"<text>" [[TEE] TO <output>]'),
    ("WRITE CREATE_TABLE FROM", "<filename> [TO <output>]"),
    ("WRITE SCRIPT", "<script_name> [[APPEND] TO <output_file>]"),
    ("ZIP", "<filename> [APPEND] TO ZIPFILE <zipfilename>"),
]

_METACOMMANDS_PLAIN = """\
Metacommands are embedded in SQL comment lines following the !x! token.
See the documentation for more complete descriptions of the metacommands.
   ASK "<question>" SUB <match_string>
   AUTOCOMMIT ON|OFF
   BEGIN BATCH / END BATCH / ROLLBACK BATCH
   BEGIN SCRIPT / END SCRIPT
   BEGIN SQL / END SQL
   CANCEL_HALT ON|OFF
   CD <directory>
   CONNECT <alias> [AS <alias_name>]
   COPY <source_file> TO <dest_file>
   DEBUG ON|OFF
   DEFINE SUB <variable> [AS] <value>
   EXPORT QUERY <queryname> [AS <alias>] ...
   EXPORT <queryname> TO <format> <filename> ...
   HALT [ON] ERROR|CANCEL
   IF <condition> / ELSE / ENDIF
   IMPORT FILE <filename> [OPTIONS ...]
   IMPORT TABLE <tablename> FROM FILE <filename> [OPTIONS ...]
   LOOP <n> TIMES / END LOOP
   LOOP WHILE <condition> / END LOOP
   LOOP UNTIL <condition> / END LOOP
   ON CANCEL_HALT ...
   ON ERROR_HALT ...
   PAUSE [<text>]
   PROMPT ACTION ...
   PROMPT ENTRY_FORM ...
   PROMPT MENU ...
   PROMPT OPENFILE ...
   PROMPT SAVEFILE ...
   PROMPT DIRECTORY ...
   PROMPT MAP ...
   RECONNECT
   ROLLBACK
   SERVE <queryname> ...
   SET AUTOCOMMIT ON|OFF
   SHELL (<command>)
   SHOW WARNINGS ON|OFF
   SUB <variable> [AS] <value>
   SUB_TEMPFILE <variable>
   SYSTEM_CMD (<operating system command line>)
   TIMER ON|OFF
   USE <alias_name>
   WAIT_UNTIL <Boolean_expression> <HALT|CONTINUE> AFTER <n> SECONDS
   WRITE "<text>" [[TEE] TO <output>]
   WRITE CREATE_TABLE FROM <filename> [TO <output>]
   WRITE SCRIPT <script_name> [[APPEND] TO <output_file>]
   ZIP <filename> [APPEND] TO ZIPFILE <zipfilename>"""


def _print_metacommands() -> None:
    """Print the metacommands table using Rich."""
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
    for name, syntax in _METACOMMANDS:
        table.add_row(name, syntax)
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
