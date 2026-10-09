"""Readable syntax for every metacommand, conditional test and system variable.

The dispatch table recognizes metacommands with regular expressions, which
tell a reader nothing.  This module holds what a person should see instead:
the syntax lines from the reference documentation, a one-line summary and a
link to the section that explains it.  Editors (``execsql lsp``) and
``execsql list metacommands`` read it; ``tests/test_reference.py`` keeps it in
step with the dispatch table, the conditional tests and the docs.

Syntax lines use the documentation's notation: ``<name>`` is a value to fill
in, ``[...]`` is optional and ``A|B`` is a choice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "DOCS_URL",
    "Condition",
    "Metacommand",
    "SystemVariable",
    "condition",
    "conditions",
    "metacommand",
    "metacommands",
    "system_variable",
    "system_variables",
    "to_snippet",
]

DOCS_URL = "https://execsql2.readthedocs.io/en/latest/reference/"


@dataclass(frozen=True)
class Metacommand:
    """A metacommand keyword as a reader sees it."""

    keyword: str
    category: str
    forms: tuple[str, ...]
    summary: str
    anchor: str

    @property
    def url(self) -> str:
        return f"{DOCS_URL}metacommands/#{self.anchor}"

    @property
    def snippet(self) -> str:
        return to_snippet(self.forms[0])


@dataclass(frozen=True)
class Condition:
    """A conditional test (``HASROWS(...)``) or operator usable in IF, LOOP and ASSERT."""

    name: str
    forms: tuple[str, ...]
    summary: str
    anchor: str

    @property
    def url(self) -> str:
        return f"{DOCS_URL}metacommands/#{self.anchor}"

    @property
    def snippet(self) -> str:
        return to_snippet(self.forms[0])


@dataclass(frozen=True)
class SystemVariable:
    """A variable execsql defines and maintains (``$CURRENT_DATE``, ``$ARG_x``, ...)."""

    name: str
    summary: str
    doc: str  # "<page>.md#<anchor>" under the reference docs

    @property
    def url(self) -> str:
        page, _, anchor = self.doc.partition("#")
        return f"{DOCS_URL}{page.removesuffix('.md')}/#{anchor}"


def metacommands() -> tuple[Metacommand, ...]:
    return _METACOMMANDS


def metacommand(keyword: str) -> Metacommand | None:
    """The entry for *keyword* (any case), or ``None``."""
    return _BY_KEYWORD.get(" ".join(keyword.upper().split()))


def conditions() -> tuple[Condition, ...]:
    return _CONDITIONS


def condition(name: str) -> Condition | None:
    return _BY_CONDITION.get(name.upper())


def system_variables() -> tuple[SystemVariable, ...]:
    return _SYSTEM_VARIABLES


def system_variable(name: str) -> SystemVariable | None:
    """The entry for ``$NAME``; ``$ARG_3`` and ``$COUNTER_2`` find ``$ARG_x`` and ``$COUNTER_x``."""
    name = name.upper()
    if not name.startswith("$"):
        name = "$" + name
    return _BY_VARIABLE.get(name) or _BY_VARIABLE.get(re.sub(r"_\d+$", "_X", name))


# ---------------------------------------------------------------------------
# Snippets
# ---------------------------------------------------------------------------

_RX_OPTIONAL = re.compile(r"\s*\[[^\[\]]*\]")
_RX_TOKEN = re.compile(r"<<(\w[^<>]*)>>|<([^<>]+)>(?:\|\S+)?|\b([A-Z_]+(?:\|[A-Z_]+)+)\b")


def to_snippet(form: str) -> str:
    """Turn a syntax line into an LSP snippet with a tab stop per value.

    Optional parts are left out, each ``<value>`` becomes a placeholder (a
    ``<<query>>`` keeps its literal ``<<`` ``>>``) and each ``A|B`` keyword
    choice becomes a choice list:
    ``EXPORT <table> TO <file>|stdout AS <format> [DESCRIPTION "<d>"]``
    gives ``EXPORT ${1:table} TO ${2:file} AS ${3:format}``.
    """
    text = form
    while True:  # drop optional parts, innermost first
        stripped = _RX_OPTIONAL.sub("", text)
        if stripped == text:
            break
        text = stripped
    text = text.replace("\\", "\\\\").replace("$", "\\$").replace("}", "\\}")
    counter = 0

    def placeholder(m: re.Match[str]) -> str:
        nonlocal counter
        counter += 1
        if m.group(3):
            return f"${{{counter}|{m.group(3).replace('|', ',')}|}}"
        if m.group(1):  # a query is written between literal << and >>
            return f"<<${{{counter}:{m.group(1).strip()}}}>>"
        return f"${{{counter}:{m.group(2).strip()}}}"

    return _RX_TOKEN.sub(placeholder, text)


# ---------------------------------------------------------------------------
# Data — generated once from docs/reference/metacommands.md and
# docs/reference/substitution_vars.md, then edited by hand.
# ---------------------------------------------------------------------------

_METACOMMANDS: tuple[Metacommand, ...] = (
    Metacommand(
        "ANDIF",
        "control",
        ("ANDIF(<conditional expression>)",),
        "Adds a condition that must also be true for the preceding IF or ELSEIF.",
        "if_cmd",
    ),
    Metacommand(
        "APPEND SCRIPT",
        "action",
        ("APPEND SCRIPT <script_2> TO <script_1>",),
        "Adds the statements of one SCRIPT block to the end of another (same as EXTEND SCRIPT).",
        "extend-script",
    ),
    Metacommand(
        "ASK",
        "prompt",
        ('ASK "<question>" SUB <match_string>',),
        "Asks a yes/no question on the console and assigns the answer to a variable.",
        "ask",
    ),
    Metacommand(
        "ASSERT",
        "action",
        ("ASSERT <condition>", 'ASSERT <condition> "<failure message>"', "ASSERT <condition> '<failure message>'"),
        "Halts the script with a message when a condition is false.",
        "assert",
    ),
    Metacommand(
        "AUTOCOMMIT",
        "action",
        ("AUTOCOMMIT OFF", "AUTOCOMMIT ON [WITH COMMIT|ROLLBACK]"),
        "Turns automatic commit of each SQL statement on or off.",
        "autocommit",
    ),
    Metacommand(
        "BEGIN BATCH",
        "block",
        ("BEGIN BATCH",),
        "Starts a batch: statements are committed together at END BATCH, or rolled back.",
        "batch",
    ),
    Metacommand(
        "BEGIN SCRIPT",
        "block",
        (
            "BEGIN SCRIPT <script_name>",
            "BEGIN SCRIPT <script_name> WITH PARAMETERS (param1[, param2[,..]])",
            "BEGIN SCRIPT <script_name>(param1, param2=default_value)",
        ),
        "Starts a named block of statements that EXECUTE SCRIPT runs.",
        "beginscript",
    ),
    Metacommand(
        "BEGIN SQL",
        "block",
        ("BEGIN SQL",),
        "Starts a block of lines run as one SQL statement (for bodies containing semicolons).",
        "beginsql",
    ),
    Metacommand(
        "BREAK",
        "control",
        ("BREAK",),
        "Leaves the current LOOP, SCRIPT or included file immediately.",
        "break",
    ),
    Metacommand(
        "BREAKPOINT",
        "action",
        ("BREAKPOINT",),
        "Pauses the script and opens the interactive debug prompt.",
        "breakpoint",
    ),
    Metacommand(
        "CANCEL_HALT",
        "control",
        ("CANCEL_HALT ON|OFF",),
        "Whether a canceled dialog halts the script (ON, the default) or lets it continue.",
        "cancel_halt",
    ),
    Metacommand("CD", "action", ("CD <directory>",), "Changes the current working directory.", "cd"),
    Metacommand(
        "CONFIG",
        "config",
        (
            "CONFIG BOOLEAN_INT YES|NO",
            "CONFIG BOOLEAN_WORDS YES|NO",
            "CONFIG CLEAN_COLUMN_HEADERS YES|NO",
            "CONFIG CONSOLE WAIT_WHEN_DONE YES|NO",
            "CONFIG CONSOLE WAIT_WHEN_ERROR YES|NO",
            "CONFIG CREATE_COLUMN_HEADERS YES|NO",
            "CONFIG DAO_FLUSH_DELAY_SECS <seconds>",
            "CONFIG DEDUP_COLUMN_HEADERS YES|NO",
            "CONFIG DELETE_EMPTY_COLUMNS YES|NO",
            "CONFIG EMPTY_ROWS YES|NO",
            "CONFIG EMPTY_STRINGS YES|NO",
            "CONFIG EXPORT_ROW_BUFFER <n>",
            "CONFIG FOLD_COLUMN_HEADERS NO|LOWER|UPPER",
            "CONFIG GUI_LEVEL <n>",
            "CONFIG HDF5_TEXT_LEN <n>",
            "CONFIG IMPORT_ROW_BUFFER <n>",
            "CONFIG LOG_DATAVARS YES|NO",
            "CONFIG LOG_SQL YES|NO",
            "CONFIG LOG_WRITE_MESSAGES YES|NO",
            "CONFIG MAKE_EXPORT_DIRS YES|NO",
            "CONFIG MAX_INT <integer_value>",
            "CONFIG ONLY_STRINGS YES|NO",
            "CONFIG QUOTE_ALL_TEXT YES|NO",
            "CONFIG REPLACE_NEWLINES YES|NO",
            "CONFIG SCAN_LINES <n>",
            "CONFIG SHOW_PROGRESS YES|NO",
            "CONFIG TRIM_COLUMN_HEADERS NONE|BOTH|LEFT|RIGHT",
            "CONFIG TRIM_STRINGS YES|NO",
            "CONFIG WRITE_PREFIX <text>",
            "CONFIG WRITE_PREFIX CLEAR",
            "CONFIG WRITE_SUFFIX <text>",
            "CONFIG WRITE_SUFFIX CLEAR",
            "CONFIG WRITE_WARNINGS YES|NO",
            "CONFIG ZIP_BUFFER_MB <n>",
        ),
        "Changes a configuration setting while the script runs.",
        "config",
    ),
    Metacommand(
        "CONNECT",
        "action",
        (
            "CONNECT TO POSTGRESQL(SERVER=<server_name>, DB=<database_name> [, USER=<user>, NEED_PWD=TRUE|FALSE] [, PORT=<port_number>] [, PASSWORD=<password>] [, ENCODING=<encoding>] [, NEW]) AS <alias_name>",
            "CONNECT USER TO POSTGRESQL(SERVER=<server_name>, DB=<database_name> [, PORT=<port_number>] [, ENCODING=<encoding>]) AS <alias_name>",
            "CONNECT TO SQLITE(FILE=<database_file> [, NEW]) AS <alias_name>",
            "CONNECT TO ACCESS(FILE=<database_file> [, NEED_PWD=TRUE|FALSE] [, PASSWORD=<password>] [, ENCODING=<encoding>]) AS <alias_name>",
            "CONNECT TO SQLSERVER(SERVER=<server_name>, DB=<database_name> [, USER=<user>, NEED_PWD=TRUE|FALSE]  [, PORT=<port_number>] [, PASSWORD=<password>] [, ENCODING=<encoding>]) AS <alias_name>",
            "CONNECT USER TO SQLSERVER(SERVER=<server_name>, DB=<database_name> [, PORT=<port_number>] [, ENCODING=<encoding>]) AS <alias_name>",
            "CONNECT TO MYSQL(SERVER=<server_name>, DB=<database_name> [, USER=<user>, NEED_PWD=TRUE|FALSE]  [, PORT=<port_number>] [, PASSWORD=<password>] [, ENCODING=<encoding>]) AS <alias_name>",
            "CONNECT USER TO MYSQL(SERVER=<server_name>, DB=<database_name> [, PORT=<port_number>] [, ENCODING=<encoding>]) AS <alias_name>",
            "CONNECT TO MARIADB(SERVER=<server_name>, DB=<database_name> [, USER=<user>, NEED_PWD=TRUE|FALSE]  [, PORT=<port_number>] [, PASSWORD=<password>] [, ENCODING=<encoding>]) AS <alias_name>",
            "CONNECT USER TO MARIADB(SERVER=<server_name>, DB=<database_name> [, PORT=<port_number>] [, ENCODING=<encoding>]) AS <alias_name>",
            "CONNECT TO DUCKDB(FILE=<database_file> [, NEW]) AS <alias_name>",
            "CONNECT TO FIREBIRD(SERVER=<server_name>, DB=<database_name> [, USER=<user>, NEED_PWD=TRUE|FALSE]  [, PORT=<port_number>] [, ENCODING=<encoding>]) AS <alias_name>",
            "CONNECT USER TO FIREBIRD(SERVER=<server_name>, DB=<database_name> [, PORT=<port_number>] [, ENCODING=<encoding>]) AS <alias_name>",
            "CONNECT TO ORACLE(SERVER=<server_name>, DB=<service_name> [, USER=<user>, NEED_PWD=TRUE|FALSE]  [, PORT=<port_number>] [, PASSWORD=<password>] [, ENCODING=<encoding>]) AS <alias_name>",
            "CONNECT USER TO ORACLE(SERVER=<server_name>, DB=<service_name> [, PORT=<port_number>] [, ENCODING=<encoding>]) AS <alias_name>",
            "CONNECT TO DSN(DSN=<DSN_name> [, USER=<user>, NEED_PWD=TRUE|FALSE] [, PASSWORD=<password>] [, ENCODING=<encoding>]) AS <alias_name>",
        ),
        "Opens a connection to another database and gives it an alias for USE and COPY.",
        "connect",
    ),
    Metacommand(
        "CONSOLE",
        "prompt",
        (
            "CONSOLE ON|OFF",
            "CONSOLE HIDE|SHOW",
            "CONSOLE HEIGHT <lines>",
            "CONSOLE WIDTH <chars>",
            'CONSOLE STATUS "<message>"',
            "CONSOLE PROGRESS <number> [/ <total>]",
            "CONSOLE SAVE [APPEND] TO <filename>",
            'CONSOLE WAIT ["<message>"]',
        ),
        "Opens (ON) or closes (OFF) a GUI console that WRITE output goes to.",
        "console",
    ),
    Metacommand(
        "COPY",
        "action",
        ("COPY <table1_or_view> FROM <alias_name_1> TO [NEW|REPLACEMENT] <table2> IN <alias_name_2>",),
        "Copies a table or view from one database to a table in another.",
        "copy",
    ),
    Metacommand(
        "COPY QUERY",
        "action",
        ("COPY QUERY <<query>> FROM <alias_name_1> TO [NEW|REPLACEMENT] <table> IN <alias_name_2>",),
        "Copies the result of a query from one database to a table in another.",
        "copy-query",
    ),
    Metacommand(
        "DEBUG",
        "action",
        (
            "DEBUG LOG [LOCAL] [USER] SUBVARS",
            "DEBUG LOG CONFIG",
            "DEBUG WRITE [LOCAL] [USER] SUBVARS [[APPEND] TO <filename>]",
            "DEBUG WRITE CONFIG [[APPEND] TO <filename>]",
            "DEBUG WRITE ODBC_DRIVERS [[APPEND] TO <filename>]",
            "DEBUG WRITE METACOMMANDLIST TO <filename>",
            "DEBUG WRITE COMMANDLISTSTACK",
            "DEBUG WRITE IFLEVELS",
        ),
        "Writes internal state to the log file (`LOG` form) or to the terminal or a file (`WRITE` form).",
        "debug",
    ),
    Metacommand(
        "DISCONNECT",
        "action",
        ("DISCONNECT [[FROM] <alias>]",),
        "Closes the current database connection, or the one with the given alias.",
        "disconnect",
    ),
    Metacommand(
        "ELSE",
        "control",
        ("ELSE",),
        "Starts the statements run when no IF or ELSEIF condition was true.",
        "if_cmd",
    ),
    Metacommand(
        "ELSEIF",
        "control",
        ("ELSEIF(<conditional expression>)",),
        "Tests another condition when the IF and earlier ELSEIF conditions were false.",
        "if_cmd",
    ),
    Metacommand(
        "EMAIL",
        "action",
        (
            'EMAIL FROM <from_address> TO <to_addresses> SUBJECT "<subject>" MESSAGE "<message_text>" [MESSAGE_FILE "<filename>"] [ATTACH_FILE "<attachment_filename>"]',
        ),
        "Sends an email.",
        "email",
    ),
    Metacommand("END BATCH", "block", ("END BATCH",), "Ends a batch and commits its statements.", "batch"),
    Metacommand("END SCRIPT", "block", ("END SCRIPT [script_name]",), "Ends a named SCRIPT block.", "beginscript"),
    Metacommand("END SQL", "block", ("END SQL",), "Ends a BEGIN SQL block.", "beginsql"),
    Metacommand("ENDIF", "control", ("ENDIF",), "Ends an IF block.", "if_cmd"),
    Metacommand(
        "ERROR_HALT",
        "control",
        ("ERROR_HALT ON|OFF",),
        "Whether a SQL error halts the script (ON, the default) or lets it continue.",
        "error_halt",
    ),
    Metacommand(
        "EXECUTE SCRIPT",
        "action",
        (
            "EXECUTE SCRIPT [IF EXISTS] <script_name>",
            "EXECUTE SCRIPT [IF EXISTS] <script_name> WHILE (<conditional expression>)",
            "EXECUTE SCRIPT [IF EXISTS] <script_name> UNTIL (<conditional expression>)",
            "EXECUTE SCRIPT [IF EXISTS] <script_name> WITH ARGUMENTS (param1=val1 [, param2=val2 [,...]])",
            "EXECUTE SCRIPT [IF EXISTS] <script_name> WITH ARGUMENTS (param1=val1 [, param2=val2 [,...]]) WHILE (<conditional_expression>)",
            "EXECUTE SCRIPT [IF EXISTS] <script_name> WITH ARGUMENTS (param1=val1 [, param2=val2 [,...]]) UNTIL (<conditional_expression>)",
            'EXECUTE SCRIPT do_me_over UNTIL (EQUAL("!!", "10"))',
            'EXECUTE SCRIPT do_me_over UNTIL (EQUAL("!!loop_ctr!!", "10"))',
        ),
        "Runs a named SCRIPT block, optionally with arguments, WHILE or UNTIL a condition.",
        "executescript",
    ),
    Metacommand(
        "EXPORT",
        "action",
        (
            'EXPORT <table_or_view> [TEE] [APPEND] TO <filename>|stdout [IN ZIPFILE <zipfilename>] AS <format> [DESCRIPTION "<description>"]',
            "EXPORT <table_or_view> [TEE] [APPEND] TO <filename>|stdout [IN ZIPFILE <zipfilename>] WITH TEMPLATE <template_file>",
        ),
        "Exports data to a file.",
        "export",
    ),
    Metacommand(
        "EXPORT QUERY",
        "action",
        (
            'EXPORT QUERY <<query>> [TEE] [APPEND] TO <filename>|stdout [IN ZIPFILE <zipfilename>] AS <format> [DESCRIPTION "<description>"]',
            "EXPORT QUERY <<query>> [TEE] [APPEND] TO <filename>|stdout [IN ZIPFILE <zipfilename>] WITH TEMPLATE <template_file>",
        ),
        "Exports the result of a query to a file.",
        "export-query",
    ),
    Metacommand(
        "EXPORT_METADATA",
        "action",
        (
            "EXPORT_METADATA [APPEND] [ALL] TO <filename>|stdout [IN ZIPFILE <zipfilename>] AS <format>",
            "EXPORT_METADATA [ALL] INTO [NEW|REPLACEMENT] TABLE <table_name>",
        ),
        "Writes the metadata recorded for every EXPORT so far (table, file, description, date, user).",
        "export_metadata",
    ),
    Metacommand(
        "EXTEND SCRIPT",
        "action",
        (
            "EXTEND SCRIPT <script> WITH SQL <sql_statement>",
            "EXTEND SCRIPT <script> WITH METACOMMAND <metacommand>",
            "EXTEND SCRIPT <script_1> WITH SCRIPT <script_2>",
        ),
        "Adds statements to the end of an existing SCRIPT block.",
        "extend-script",
    ),
    Metacommand(
        "HALT",
        "control",
        ('HALT [[MESSAGE] "<error_message>" [TEE TO <outfile>]] [DISPLAY <table_or_view>] [EXIT_STATUS <n>]',),
        "Stops the script, optionally with a message and exit status.",
        "halt",
    ),
    Metacommand(
        "IF",
        "control",
        ("IF(<conditional expression>)", "IF(<conditional expression>) <SQL statements and metacommands>"),
        "Runs the statements up to ELSEIF, ELSE or ENDIF only when a condition is true.",
        "if_cmd",
    ),
    Metacommand(
        "IMPORT",
        "action",
        (
            "IMPORT TO [NEW|REPLACEMENT] <table_name> FROM <file_name> [WITH [QUOTE <quote_char> DELIMITER <delim_char>] [ENCODING <encoding>]] [SKIP <lines>]",
            "IMPORT TO [NEW|REPLACEMENT] <table_name> FROM <file_name> SHEET <sheet_name> [SKIP <rows>]",
            "IMPORT TO [NEW|REPLACEMENT] TABLES IN [SCHEMA] <schema_name> FROM <file_name> SHEETS MATCHING <regular_expression> [SKIP <rows>]",
            "IMPORT TO [NEW|REPLACEMENT] <table_name> FROM EXCEL <file_name> SHEET <sheet_name> [SKIP <rows>] [ENCODING <encoding>]",
            "IMPORT TO [NEW|REPLACEMENT] TABLES IN [SCHEMA] <schema_name> FROM EXCEL <file_name> SHEETS MATCHING <regular_expression> [SKIP <rows>] [ENCODING <encoding>]",
            "IMPORT TO [NEW|REPLACEMENT] <table_name> FROM PARQUET <file_name>",
            "IMPORT TO [NEW|REPLACEMENT] <table_name> FROM FEATHER <file_name>",
            "IMPORT TO [NEW|REPLACEMENT] <table_name> FROM JSON <file_name>",
        ),
        "Imports tabular data from a file into a new or existing database table.",
        "import",
    ),
    Metacommand(
        "IMPORT_FILE",
        "action",
        ("IMPORT_FILE TO TABLE <table_name> COLUMN <column_name> FROM <file_name>",),
        "Imports an entire file into a single column, on a new row, of an existing database table.",
        "import_file",
    ),
    Metacommand(
        "INCLUDE",
        "action",
        ("INCLUDE [IF EXISTS] <filename>",),
        "Runs the statements and metacommands of another script file here.",
        "include",
    ),
    Metacommand("LOG", "action", ('LOG "<message>"',), "Writes the specified message to execsql's log file.", "log"),
    Metacommand(
        "LOOP",
        "control",
        (
            "LOOP WHILE (<conditional expression>)",
            "LOOP UNTIL (<conditional expression>)",
            'LOOP UNTIL (EQUAL("!!", "10"))',
        ),
        "Repeats the statements up to END LOOP while, or until, a condition is true.",
        "loop",
    ),
    Metacommand(
        "MAX_INT",
        "action",
        ("MAX_INT <integer_value>",),
        "Sets the largest value IMPORT and COPY treat as integer rather than bigint (same as CONFIG MAX_INT).",
        "config",
    ),
    Metacommand(
        "METACOMMAND_ERROR_HALT",
        "control",
        ("METACOMMAND_ERROR_HALT ON|OFF",),
        "Whether a metacommand error halts the script (ON, the default) or lets it continue.",
        "metacommanderrorhalt",
    ),
    Metacommand(
        "ON CANCEL_HALT",
        "config",
        (
            'ON CANCEL_HALT EMAIL FROM <from_address> TO <to_addresses> SUBJECT "<subject>" MESSAGE "<message_text>" [MESSAGE_FILE "<filename>"] [ATTACH_FILE "<attachment_filename>"]',
            "ON CANCEL_HALT EMAIL CLEAR",
        ),
        "Sends an email, writes a message or runs a script when the user cancels the script at a prompt.",
        "on-cancel_halt-email",
    ),
    Metacommand(
        "ON ERROR_HALT",
        "config",
        (
            'ON ERROR_HALT EMAIL FROM <from_address> TO <to_addresses> SUBJECT "<subject>" MESSAGE "<message_text>" [MESSAGE_FILE "<filename>"] [ATTACH_FILE "<attachment_filename>"]',
            "ON ERROR_HALT EMAIL CLEAR",
        ),
        "Sends an email, writes a message or runs a script when an error halts the script.",
        "on-error_halt-email",
    ),
    Metacommand(
        "ORIF",
        "control",
        ("ORIF(<conditional expression>)",),
        "Adds an alternative condition to the preceding IF or ELSEIF.",
        "if_cmd",
    ),
    Metacommand(
        "PAUSE",
        "control",
        ('PAUSE "<text>" [HALT|CONTINUE AFTER <n> MINUTES|SECONDS]',),
        "Displays the specified text and pauses script processing.",
        "pause",
    ),
    Metacommand(
        "PG_UPSERT",
        "action",
        ("PG_UPSERT FROM <staging_schema> TO <base_schema> TABLES <table1>, <table2> [options]",),
        "Performs QA-checked, FK-dependency-ordered upserts from a staging schema to a base schema on PostgreSQL.",
        "pg_upsert",
    ),
    Metacommand(
        "PG_UPSERT CHECK",
        "action",
        ("PG_UPSERT CHECK FROM <staging_schema> TO <base_schema> TABLES <table1>, <table2> [options]",),
        "Checks that staging columns exist in the base tables with compatible types; never commits.",
        "pg_upsert",
    ),
    Metacommand(
        "PG_UPSERT QA",
        "action",
        ("PG_UPSERT QA FROM <staging_schema> TO <base_schema> TABLES <table1>, <table2> [options]",),
        "Runs every pg-upsert QA check without loading; never commits.",
        "pg_upsert",
    ),
    Metacommand(
        "PG_VACUUM",
        "action",
        ("PG_VACUUM <vacuum arguments>",),
        "Runs VACUUM on the current PostgreSQL database.",
        "pg_vacuum",
    ),
    Metacommand(
        "PROMPT ACTION",
        "prompt",
        (
            'PROMPT ACTION <specification_table> MESSAGE "<text>" [DISPLAY <table_or_view>] [COMPACT <columns>] [CONTINUE] [HELP <url>]',
        ),
        "Shows a dialog of buttons, each running a named SCRIPT.",
        "prompt_action",
    ),
    Metacommand(
        "PROMPT ASK",
        "prompt",
        (
            'PROMPT ASK "<question>" SUB <match_string> [HELP <url>]',
            'PROMPT ASK "<question>" SUB <match_string> [DISPLAY <table_or_view>] [HELP <url>]',
            'PROMPT ASK "<question>" SUB <match_string> COMPARE <table1> [IN <alias1>] AND|BESIDE <table2> [IN <alias2>] KEY(<col1>[, col2[, col3...]]) [HELP <url>]',
        ),
        "Asks a yes/no question in a dialog and assigns the answer to a variable.",
        "prompt_ask",
    ),
    Metacommand(
        "PROMPT ASK COMPARE",
        "prompt",
        (
            'PROMPT ASK "<question>" SUB <match_string> COMPARE <table1> [IN <alias1>] AND|BESIDE <table2> [IN <alias2>] KEY(<col1>[, <col2>...]) [HELP <url>]',
        ),
        "Shows two tables side by side or stacked and asks a yes/no question about them.",
        "prompt_ask",
    ),
    Metacommand(
        "PROMPT COMPARE",
        "prompt",
        (
            'PROMPT COMPARE <table1> [IN <alias1>] AND|BESIDE <table2> [IN <alias2>] KEY(<col1>[, col2[, col3...]]) [HELP <url>] MESSAGE "<text>"',
        ),
        "Displays the two specified tables in a graphical interface.",
        "prompt_compare",
    ),
    Metacommand(
        "PROMPT CONNECT",
        "prompt",
        ('PROMPT [MESSAGE "<text>"] CONNECT AS <alias> [HELP <url>]',),
        "Asks for connection details in a dialog and connects them under an alias.",
        "prompt_connect",
    ),
    Metacommand(
        "PROMPT CREDENTIALS",
        "prompt",
        ('PROMPT [MESSAGE "<text>"] CREDENTIALS <user_var> <pw_var>',),
        "Asks for a user name and password in a dialog and assigns them to variables.",
        "prompt-credentials",
    ),
    Metacommand(
        "PROMPT DIRECTORY",
        "prompt",
        ("PROMPT DIRECTORY SUB <match_string> [FROM <starting_dir>]",),
        "Asks for an existing directory in a dialog and assigns its full path to a variable.",
        "prompt-directory",
    ),
    Metacommand(
        "PROMPT DISPLAY",
        "prompt",
        ('PROMPT DISPLAY <table_or_view_name> MESSAGE "<text>" [HELP <url>]',),
        "Shows a table or view in a window with Continue and Cancel buttons.",
        "prompt",
    ),
    Metacommand(
        "PROMPT ENTER_SUB",
        "prompt",
        (
            'PROMPT ENTER_SUB <match_string> [PASSWORD] MESSAGE "<text>" [DISPLAY <table_or_view>] [TYPE INT|FLOAT|BOOL|IDENT] [LCASE|UCASE] [INITIALLY "<text>"] [HELP <url>]',
        ),
        "Asks for a value in a dialog and assigns it to a variable.",
        "prompt_enter",
    ),
    Metacommand(
        "PROMPT ENTRY_FORM",
        "prompt",
        ('PROMPT ENTRY_FORM <specification_table> [HELP <url>] MESSAGE "<text>" [DISPLAY <table_or_view>]',),
        "Shows a data entry form defined by a table and assigns the entries to variables.",
        "prompt-entry_form",
    ),
    Metacommand(
        "PROMPT MAP",
        "prompt",
        (
            'PROMPT MESSAGE "<text>" MAP <table_or_view> LAT <lat_col> LON <lon_col> [LABEL <label_col>] [COLOR <color_col>] [SYMBOL <symbol_col>]',
        ),
        "Opens a dialog showing the rows of the specified table or view as points on an interactive map.",
        "prompt_map",
    ),
    Metacommand(
        "PROMPT MESSAGE",
        "prompt",
        ('PROMPT [MESSAGE] "<text>"',),
        "Displays the specified text in a dialog box with a single 'Close' button.",
        "prompt-message",
    ),
    Metacommand(
        "PROMPT OPENFILE",
        "prompt",
        ("PROMPT OPENFILE SUB <filepath_var> [filename_var] [path_var] [ext_var] [basefn_var] [FROM <starting_dir>]",),
        "Asks for an existing file in a dialog and assigns its full path to a variable.",
        "prompt-openfile",
    ),
    Metacommand(
        "PROMPT PAUSE",
        "prompt",
        ('PROMPT PAUSE "<text>" [HALT|CONTINUE AFTER <n> MINUTES|SECONDS]',),
        "Displays the specified text in a GUI dialog and pauses script processing.",
        "prompt-pause",
    ),
    Metacommand(
        "PROMPT SAVEFILE",
        "prompt",
        ("PROMPT SAVEFILE SUB <filepath_var> [filename_var] [path_var] [ext_var] [basefn_var] [FROM <starting_dir>]",),
        "Asks for a file name to save to in a dialog and assigns its full path to a variable.",
        "prompt-savefile",
    ),
    Metacommand(
        "PROMPT SELECT_ROWS",
        "prompt",
        ('PROMPT SELECT_ROWS FROM <table1> INTO <table2> [HELP <url>] MESSAGE "<prompt_text>"',),
        "Shows two tables and lets the user copy rows from the first into the second.",
        "prompt-select_rows",
    ),
    Metacommand(
        "PROMPT SELECT_SUB",
        "prompt",
        ('PROMPT SELECT_SUB <table_or_view> MESSAGE "<prompt_text>" [CONTINUE] [HELP <url>]',),
        "Shows a table, lets the user pick one row, and assigns it to @column variables.",
        "prompt_selsub",
    ),
    Metacommand(
        "RESET COUNTER",
        "action",
        ("RESET COUNTER <counter_no>", "RESET COUNTERS"),
        "Resets a counter variable so its next reference returns 1.",
        "reset-counter",
    ),
    Metacommand(
        "RESET DIALOG_CANCELED",
        "action",
        ("RESET DIALOG_CANCELED",),
        "Sets the internal 'dialog canceled' flag to False.",
        "reset-dialog_canceled",
    ),
    Metacommand("RM_FILE", "action", ("RM_FILE <file_name>",), "Deletes the specified file.", "rm_file"),
    Metacommand(
        "RM_SUB",
        "action",
        ("RM_SUB <match_string>",),
        "Deletes the specified user-created substitution variable.",
        "rm_sub",
    ),
    Metacommand(
        "ROLLBACK BATCH",
        "block",
        ("ROLLBACK [BATCH]",),
        "Rolls back the statements of the current batch.",
        "batch",
    ),
    Metacommand(
        "RUN",
        "action",
        ("RUN <procedure_name>",),
        "Runs a stored procedure or function (same as EXECUTE).",
        "execute",
    ),
    Metacommand(
        "SELECT_SUB",
        "action",
        ("SELECT_SUB <table_or_view>",),
        "Assigns the first row of a table or view to @column variables.",
        "select_sub",
    ),
    Metacommand(
        "SERVE",
        "action",
        ("SERVE <filename> AS <format>",),
        "Copies the specified file to stdout with Content-Type and Content-Disposition headers.",
        "serve",
    ),
    Metacommand(
        "SET COUNTER",
        "action",
        ("SET COUNTER <counter_no> TO <numeric_expression>",),
        "Assigns the value of the specified numeric expression to the counter.",
        "set-counter",
    ),
    Metacommand(
        "SHOW SCRIPTS",
        "action",
        ("SHOW SCRIPTS [<name>]",),
        "Lists the SCRIPT blocks defined so far, or the details of one.",
        "show_scripts",
    ),
    Metacommand(
        "SUB",
        "action",
        ("SUB <match_string> <replacement_string>",),
        "Defines a substitution variable.",
        "subcmd",
    ),
    Metacommand(
        "SUBDATA",
        "action",
        ("SUBDATA <match_string> <table_or_view_name>",),
        "Assigns the first value of a table or view to a substitution variable.",
        "subdata",
    ),
    Metacommand(
        "SUB_ADD",
        "action",
        ("SUB_ADD <match_string> <numeric_expression>",),
        "Adds a numeric value to a substitution variable.",
        "sub_add",
    ),
    Metacommand(
        "SUB_APPEND",
        "action",
        ("SUB_APPEND <match_string> <new_line>",),
        "Appends a line of text to a substitution variable.",
        "sub_append",
    ),
    Metacommand(
        "SUB_DECRYPT",
        "action",
        ("SUB_DECRYPT <sub_var_name> <encrypted_text>",),
        "Creates a substitution variable containing an unencrypted version of the given encrypted_text.",
        "sub_decrypt",
    ),
    Metacommand(
        "SUB_EMPTY",
        "action",
        ("SUB_EMPTY <match_string>",),
        "Defines a substitution variable containing an empty string.",
        "sub_empty",
    ),
    Metacommand(
        "SUB_ENCRYPT",
        "action",
        ("SUB_ENCRYPT <sub_var_name> <plaintext>",),
        "Creates a substitution variable containing an encrypted version of the given plaintext.",
        "sub_encrypt",
    ),
    Metacommand(
        "SUB_INI",
        "action",
        ("SUB_INI [FILE] <filename> [SECTION] <section>",),
        "Assigns substitution variables as defined in the specified section of an INI file.",
        "sub_ini",
    ),
    Metacommand(
        "SUB_LOCAL",
        "action",
        ("SUB_LOCAL <match_string> <replacement_string>",),
        "Operates identically to the SUB metacommand, but always defines a local substitution variable.",
        "sub_local",
    ),
    Metacommand(
        "SUB_QUERYSTRING",
        "action",
        ("SUB_QUERYSTRING <query_string>",),
        "Creates a substitution variable for each parameter of a URL query string.",
        "sub_querystring",
    ),
    Metacommand(
        "SUB_TEMPFILE",
        "action",
        ("SUB_TEMPFILE <match_string>",),
        "Assigns a new temporary file name to a variable.",
        "sub_tempfile",
    ),
    Metacommand(
        "SYSTEM_CMD",
        "action",
        ("SYSTEM_CMD ( <operating system command line> ) [CONTINUE]",),
        "Runs an operating system command.",
        "system_cmd",
    ),
    Metacommand("TIMER", "config", ("TIMER ON|OFF",), "Starts or stops an internal timer.", "timer"),
    Metacommand(
        "USE",
        "action",
        ("USE <alias_name>",),
        "Makes the database with the given alias the one later statements run against.",
        "use",
    ),
    Metacommand(
        "WAIT_UNTIL",
        "control",
        (
            "WAIT_UNTIL <conditional_expression> HALT|CONTINUE AFTER <n> SECONDS",
            'WAIT_UNTIL EQUALS("1","0") CONTINUE AFTER 1 SECONDS',
        ),
        "Suspends execution of the SQL script until the specified conditional expression becomes true.",
        "wait_until",
    ),
    Metacommand(
        "WRITE",
        "action",
        ('WRITE "<text>" [[TEE] TO <output>]',),
        "Writes the specified text to the console or a file, or both.",
        "write",
    ),
    Metacommand(
        "WRITE CREATE_TABLE",
        "action",
        (
            'WRITE CREATE_TABLE <table_name> FROM <file_name> [WITH QUOTE <quote_char> DELIMITER <delim_char>] [ENCODING <encoding>] [SKIP <lines>] [COMMENT "<comment_text>"] [TO <output>]',
            'WRITE CREATE_TABLE <table_name> FROM <file_name> SHEET <sheet_name> [SKIP <rows>] [COMMENT "<comment_text>"] [TO <output>]',
            'WRITE CREATE_TABLE <table_name> FROM EXCEL <file_name> SHEET <sheet_name> [SKIP <rows>] [ENCODING <encoding>] [COMMENT "<comment_text>"] [TO <output>]',
            'WRITE CREATE_TABLE <table_name> FROM <table_name> IN <alias> [COMMENT "<comment_text>"] [TO <output>]',
        ),
        "Writes the CREATE TABLE statement IMPORT would use for a file, without importing it.",
        "write-create_table",
    ),
    Metacommand(
        "WRITE SCRIPT",
        "action",
        ("WRITE SCRIPT <script_name> [[APPEND] TO <output_file>]",),
        "Writes the text of a SCRIPT block.",
        "write-script",
    ),
    Metacommand(
        "ZIP",
        "action",
        ("ZIP <filename> [APPEND] TO ZIPFILE <zipfilename>",),
        "Adds a file to a zip file.",
        "zip",
    ),
)

_CONDITIONS: tuple[Condition, ...] = (
    Condition(
        "ALIAS_DEFINED",
        ("ALIAS_DEFINED(<alias>)",),
        "Evaluates whether a database connection has been made using the specified alias.",
        "alias_defined",
    ),
    Condition(
        "COLUMN_EXISTS",
        ("COLUMN_EXISTS(<column_name> IN <table_name>)",),
        "Evaluates whether there is a column of the given name in the specified database table.",
        "column_exists",
    ),
    Condition("CONSOLE_ON", ("CONSOLE_ON",), "Evaluates whether or not execsql's CONSOLE is on.", "console_on"),
    Condition(
        "CONTAINS",
        ('CONTAINS("<string1>", "<string2>" [, I])',),
        "Evaluates whether string2 is contained within string1.",
        "contains",
    ),
    Condition(
        "DATABASE_NAME",
        ("DATABASE_NAME(<database_name>)",),
        "Evaluates whether the current database name matches the one specified.",
        "database_name",
    ),
    Condition("DBMS", ("DBMS(<dbms_name>)",), "Evaluates whether the current DBMS matches the one specified.", "dbms"),
    Condition(
        "DIALOG_CANCELED",
        ("DIALOG_CANCELED()",),
        "Whether the last dialog was canceled (Cancel, Escape or closing the window).",
        "dialog_canceled",
    ),
    Condition(
        "DIRECTORY_EXISTS",
        ("DIRECTORY_EXISTS(<directory_name>)",),
        "Evaluates whether there is an existing directory with the given name.",
        "directory_exists",
    ),
    Condition(
        "ENDS_WITH",
        ('ENDS_WITH("<string1>", "<string2>" [, I])',),
        "Evaluates whether string1 ends with string2.",
        "ends_with",
    ),
    Condition("EQUAL", ('EQUAL("<string_1>", "<string_2>")',), "Evaluates whether the two values are equal.", "equals"),
    Condition(
        "FILE_EXISTS",
        ("FILE_EXISTS(<filename>)",),
        "Evaluates whether there is a disk file of the given name.",
        "file_exists",
    ),
    Condition(
        "HASROWS",
        ("HASROWS(<table_or_view>)",),
        "Evaluates whether the specified table or view has a non-zero number of rows.",
        "hasrows",
    ),
    Condition(
        "IDENTICAL",
        ('IDENTICAL("<string_1>", "<string_2>")',),
        "Evaluates whether the two quoted strings are exactly identical.",
        "identical",
    ),
    Condition(
        "IS_FALSE",
        ("IS_FALSE(<value>)",),
        "Evaluates whether the value represents False (the inverse of IS_TRUE).",
        "is_false",
    ),
    Condition(
        "IS_GT",
        ("IS_GT(<value1>, <value2>)",),
        "Evaluates whether or not the first of the specified values is greater than the second value.",
        "is_gt",
    ),
    Condition(
        "IS_GTE",
        ("IS_GTE(<value1>, <value2>)",),
        "Evaluates whether or not the first of the specified values is greater than or equal to the second value.",
        "is_gte",
    ),
    Condition(
        "IS_NULL",
        ('IS_NULL("<value>")',),
        "Evaluates whether the value is empty (a zero-length string).",
        "is_null",
    ),
    Condition(
        "IS_TRUE",
        ("IS_TRUE(<value>)",),
        "Evaluates whether or not the specified value represents a Boolean value of True.",
        "is_true",
    ),
    Condition(
        "IS_ZERO",
        ("IS_ZERO(<value>)",),
        "Evaluates whether or not the specified value is equal to zero.",
        "is_zero",
    ),
    Condition(
        "METACOMMAND_ERROR",
        ("METACOMMAND_ERROR()",),
        "Evaluates whether the previous metacommand generated an error.",
        "metacommanderror",
    ),
    Condition(
        "NEWER_DATE",
        ("NEWER_DATE(<filename>, <date>)",),
        "Evaluates whether the specified file was last modified after the given date.",
        "newer_date",
    ),
    Condition(
        "NEWER_FILE",
        ("NEWER_FILE(<filename1>, <filename2>)",),
        "Evaluates whether the first of the specified files was last modified after the second of the files.",
        "newer_file",
    ),
    Condition("NOT", ("NOT <condition>",), "True when the condition is false.", "if_cmd"),
    Condition(
        "OR",
        ("<condition> OR <condition>",),
        "True when either condition is true (AND, NOT and parentheses also combine conditions).",
        "if_cmd",
    ),
    Condition(
        "ROLE_EXISTS",
        ("ROLE_EXISTS(<role_name>)",),
        "Whether a role or user exists in the current database.",
        "role_exists",
    ),
    Condition(
        "ROW_COUNT_EQ",
        ("ROW_COUNT_EQ(<table_name>, <N>)",),
        "Evaluates whether the number of rows in the specified table or view is exactly equal to the integer N.",
        "row_count_eq",
    ),
    Condition(
        "ROW_COUNT_GT",
        ("ROW_COUNT_GT(<table_name>, <N>)",),
        "Evaluates whether the number of rows in the specified table or view is strictly greater than the integer N.",
        "row_count_gt",
    ),
    Condition(
        "ROW_COUNT_GTE",
        ("ROW_COUNT_GTE(<table_name>, <N>)",),
        "Evaluates whether the number of rows in the specified table or view is greater than or equal to the integer N.",
        "row_count_gte",
    ),
    Condition(
        "ROW_COUNT_LT",
        ("ROW_COUNT_LT(<table_name>, <N>)",),
        "Evaluates whether the number of rows in the specified table or view is strictly less than the integer N.",
        "row_count_lt",
    ),
    Condition(
        "SCHEMA_EXISTS",
        ("SCHEMA_EXISTS(<schema_name>)",),
        "Evaluates whether or not the specified schema already exists in the database.",
        "schema_exists",
    ),
    Condition(
        "SCRIPT_EXISTS",
        ("SCRIPT_EXISTS(<script_name>)",),
        "Evaluates whether a script with the specified name has been created with the BEGIN SCRIPT metacommand.",
        "script_exists",
    ),
    Condition(
        "SQL_ERROR",
        ("SQL_ERROR()",),
        "Evaluates whether the previous SQL statement generated an error.",
        "sqlerror",
    ),
    Condition(
        "STARTS_WITH",
        ('STARTS_WITH("<string1>", "<string2>" [, I])',),
        "Evaluates whether string1 starts with string2.",
        "starts_with",
    ),
    Condition(
        "SUB_DEFINED",
        ("SUB_DEFINED(<match_string>)",),
        "Evaluates whether a replacement string has been defined for the specified substitution variable (matching string).",
        "sub_defined",
    ),
    Condition(
        "SUB_EMPTY",
        ("SUB_EMPTY(<match_string>)",),
        "Evaluates whether the specified substitution variable is empty (i.e., is a zero-length string).",
        "sub_empty_cond",
    ),
    Condition(
        "TABLE_EXISTS",
        ("TABLE_EXISTS(<tablename>)",),
        "Evaluates whether there is a database table of the given name.",
        "tableexists",
    ),
    Condition(
        "VIEW_EXISTS",
        ("VIEW_EXISTS(<viewname>)",),
        "Evaluates whether there is a database view of the given name.",
        "view_exists",
    ),
)

_SYSTEM_VARIABLES: tuple[SystemVariable, ...] = (
    SystemVariable(
        "$ARG_x",
        'The value of a substitution variable that has been assigned on the command line using the "-a" command-line option.',
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$AUTOCOMMIT_STATE",
        "A value indicating whether or not execsql will automatically commit each SQL statement as it is executed.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$CANCEL_HALT_STATE",
        "The value of the status flag that is set by the CANCEL_HALT metacommand.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$CONSOLE_WAIT_WHEN_DONE_STATE",
        "ON or OFF: whether the GUI console waits to be closed when the script ends.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$CONSOLE_WAIT_WHEN_ERROR_HALT_STATE",
        "ON or OFF: whether the GUI console waits to be closed when an error halts the script.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$COUNTER_x",
        "An integer value that is automatically incremented every time that it is referenced.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$CURRENT_ALIAS",
        'The alias of the database in use, or "initial".',
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$CURRENT_DATABASE",
        "The DBMS type and the name of the current database.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable("$CURRENT_DBMS", "The DBMS type of the database in use.", "substitution_vars.md#system_vars"),
    SystemVariable("$CURRENT_DIR", "The full path to the current directory.", "substitution_vars.md#system_vars"),
    SystemVariable(
        "$CURRENT_PATH",
        'The full path to the current directory, including a directory separator character (i.e., "/" or "\\\\") at the end.',
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$CURRENT_SCRIPT",
        "The file name of the script from which the current command originated.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$CURRENT_SCRIPT_NAME",
        "The base file name, without a path, of the script from which the current command originated.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$CURRENT_SCRIPT_PATH",
        "The full path of the current script's directory, ending in a path separator.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$CURRENT_DATE",
        "The current calendar date (in the format `YYYY-MM-DD`) when the current script line is run.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$CURRENT_SCRIPT_LINE",
        "The 1-based line number, within `$CURRENT_SCRIPT`, of the command currently being executed.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$CURRENT_TIME",
        "The date and time at which the current script line is run.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$CURRENT_TIME_UTC",
        "The date and time at which the current script line is run, in Universal Coordinated Time (UTC).",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$DATE_TAG",
        "The date on which execsql started processing the current script, in the format YYYYMMDD.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$DATETIME_TAG",
        "The date and time at which execsql started processing the current script, in the format YYYYMMDD_hhmm.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$DATETIME_UTC_TAG",
        "The UTC date and time the script started, as YYYYMMDD_hhmm.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$DB_NAME",
        "The name of the database currently in use, as specified on the command line or in a CONNECT metacommand.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$DB_NEED_PWD",
        'A string equal to "TRUE" or "FALSE" indicating whether or not a password was required for the database currently in use.',
        "substitution_vars.md#system_vars",
    ),
    SystemVariable("$DB_SERVER", "The server name of the database in use.", "substitution_vars.md#system_vars"),
    SystemVariable("$DB_USER", "The user name of the database in use.", "substitution_vars.md#system_vars"),
    SystemVariable(
        "$ERROR_HALT_STATE",
        "The value of the status flag that is set by the ERROR_HALT metacommand.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$ERROR_MESSAGE",
        "The message generated by any error, as it would be printed on the terminal by default.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$HOSTNAME",
        "The network name of the machine running execsql, as returned by Python's `platform.node()`.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$LAST_ERROR",
        "The text of the last SQL statement or metacommand that caused an error.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$LAST_ROWCOUNT",
        "The number of rows that were affected by the last INSERT, UPDATE, or SELECT statement.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$LAST_SQL",
        "The text of the last SQL statement that ran without error.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$METACOMMAND_ERROR_HALT_STATE",
        "The value of the status flag that is set by the METACOMMAND_ERROR_HALT metacommand.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable("$OS", "The name of the operating system.", "substitution_vars.md#system_vars"),
    SystemVariable("$PATHSEP", "The path separator used by the operating system.", "substitution_vars.md#system_vars"),
    SystemVariable(
        "$PYTHON_EXECUTABLE",
        "The path and name of the Python interpreter that is running execsql.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$RANDOM",
        "A random real number in the semi-open interval \\[0.0, 1.0).",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$RUN_ID",
        "The run identifier that is used in execsql's log file.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$SCRIPT_LINE",
        "The line number of the current script for the current command.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$SCRIPT_START_TIME",
        "The date and time at which execsql started processing the current script.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$SCRIPT_START_TIME_UTC",
        "The date and time at which execsql started processing the current script, in Universal Coordinated Time (UTC).",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$SHEETS_IMPORTED",
        "A comma-delimited list of the names of all worksheets IMPORTed when using the SHEETS MATCHING clause.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$SHEETS_TABLES",
        "Comma-separated names of the tables created by IMPORT ... SHEETS MATCHING.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$SHEETS_TABLES_VALUES",
        "The tables created by IMPORT ... SHEETS MATCHING, as quoted, parenthesized values.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$STARTING_PATH",
        "The path of the directory from which execsql was started, including a terminating path separator character.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$STARTING_SCRIPT",
        "The file name of the script specified on the command line when execsql is run.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$STARTING_SCRIPT_NAME",
        "The base file name of the script specified on the command line when execsql is run, without any path specification.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$STARTING_SCRIPT_REVTIME",
        "The date and time of the script specified on the command line when execsql is run.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$SYSTEM_CMD_EXIT_STATUS",
        "The exit status of the command executed by the SYSTEM_CMD metacommand.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable(
        "$SYSTEM_CMD_PID",
        "The process ID (PID) of the background process launched by `SYSTEM_CMD … CONTINUE`.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable("$TIMER", "The elapsed time of the script timer.", "substitution_vars.md#system_vars"),
    SystemVariable(
        "$USER",
        "The name of the person logged in when the script is started.",
        "substitution_vars.md#system_vars",
    ),
    SystemVariable("$UUID", "A new random UUID (version 4) each time it is used.", "substitution_vars.md#system_vars"),
    SystemVariable("$VERSION1", "Execsql's primary version number.", "substitution_vars.md#system_vars"),
    SystemVariable("$VERSION2", "Execsql's secondary version number.", "substitution_vars.md#system_vars"),
    SystemVariable("$VERSION3", "Execsql's tertiary version number.", "substitution_vars.md#system_vars"),
    SystemVariable(
        "$PG_UPSERT_QA_PASSED",
        "TRUE or FALSE: whether every QA check passed.",
        "metacommands.md#pg_upsert",
    ),
    SystemVariable("$PG_UPSERT_ROWS_UPDATED", "Total rows updated across all tables.", "metacommands.md#pg_upsert"),
    SystemVariable("$PG_UPSERT_ROWS_INSERTED", "Total rows inserted across all tables.", "metacommands.md#pg_upsert"),
    SystemVariable(
        "$PG_UPSERT_COMMITTED",
        "TRUE or FALSE: whether the changes were committed.",
        "metacommands.md#pg_upsert",
    ),
    SystemVariable("$PG_UPSERT_STAGING_SCHEMA", "Staging schema name used.", "metacommands.md#pg_upsert"),
    SystemVariable("$PG_UPSERT_BASE_SCHEMA", "Base schema name used.", "metacommands.md#pg_upsert"),
    SystemVariable("$PG_UPSERT_TABLES", "Comma-separated list of table names processed.", "metacommands.md#pg_upsert"),
    SystemVariable("$PG_UPSERT_METHOD", "Upsert method used.", "metacommands.md#pg_upsert"),
    SystemVariable("$PG_UPSERT_DURATION", "Elapsed time in seconds.", "metacommands.md#pg_upsert"),
    SystemVariable("$PG_UPSERT_STARTED_AT", "ISO 8601 start timestamp.", "metacommands.md#pg_upsert"),
    SystemVariable("$PG_UPSERT_FINISHED_AT", "ISO 8601 end timestamp.", "metacommands.md#pg_upsert"),
    SystemVariable("$PG_UPSERT_RESULT_JSON", "The full result as JSON.", "metacommands.md#pg_upsert"),
    SystemVariable(
        "$PG_UPSERT_CURRENT_TABLE",
        "The table being processed (updated per table).",
        "metacommands.md#pg_upsert",
    ),
    SystemVariable(
        "$PG_UPSERT_TABLE_QA_PASSED",
        "QA result for the current table (updated per table).",
        "metacommands.md#pg_upsert",
    ),
    SystemVariable(
        "$PG_UPSERT_TABLE_ROWS_UPDATED",
        "Rows updated for the current table (updated per table).",
        "metacommands.md#pg_upsert",
    ),
    SystemVariable(
        "$PG_UPSERT_TABLE_ROWS_INSERTED",
        "Rows inserted for the current table (updated per table).",
        "metacommands.md#pg_upsert",
    ),
    SystemVariable(
        "$PG_UPSERT_EXPORT_PATH",
        "Where the QA fix sheet was written, or empty if nothing was exported.",
        "metacommands.md#pg_upsert",
    ),
)

_BY_KEYWORD = {m.keyword: m for m in _METACOMMANDS}
_BY_CONDITION = {c.name: c for c in _CONDITIONS}
_BY_VARIABLE = {v.name.upper(): v for v in _SYSTEM_VARIABLES}
