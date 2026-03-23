from __future__ import annotations

"""
Module-level global runtime state for execsql.

All mutable singletons and global variables that need to be shared across
the entire codebase are declared here.  Other modules do::

    import execsql.state as _state

and then access attributes (``_state.conf``, ``_state.subvars``, etc.)
inside function/method bodies — never at class-definition time — to avoid
circular-import issues at load time.

Variable groups defined here:

- **Configuration** — ``conf`` (:class:`execsql.config.ConfigData`),
  ``logfile_encoding``.
- **Runtime flags** — ``last_command``, ``upass``, ``varlike`` regex,
  halt/cancel write-spec and mail-spec objects.
- **Execution stack** — ``commandliststack``, ``savedscripts``,
  ``loopcommandstack``, ``compiling_loop``, loop regexes and nesting counter.
- **Lazy singletons** — ``if_stack``, ``counters``, ``timer``, ``output``,
  ``dbs``, ``tempfiles``, ``export_metadata``, ``metacommandlist``,
  ``filewriter``, ``gui_console``, GUI queue/thread.
- **Version** — ``primary_vno``, ``secondary_vno``, ``tertiary_vno`` parsed
  from ``__version__``.
- **Utility functions** — ``xcmd_test()`` (evaluate a conditional string),
  ``endloop()`` (finalise a compiled loop).

The bottom of this module re-exports frequently-used names from sibling
modules so that ``_state.ErrInfo``, ``_state.runscripts``, etc. resolve
correctly even though those modules themselves import ``execsql.state``.
"""

import getpass
import re
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from execsql.config import ConfigData

# ---------------------------------------------------------------------------
# Configuration / encoding
# ---------------------------------------------------------------------------

# Configuration data, initialized in main()
conf: Optional[ConfigData] = None

# Default encodings
logfile_encoding: str = "utf8"  # Should never be changed; is not configurable.

# ---------------------------------------------------------------------------
# Runtime state variables
# ---------------------------------------------------------------------------

# The last command run.  This should be a ScriptCmd object.
last_command: Any = None

# The last user password entered via 'get_password()'
upass: Optional[str] = None

# A compiled regex to match prefixed regular expressions, used to check
# for unsubstituted variables.
varlike = re.compile(r"!![$@&~#]?\w+!!", re.I)

# A WriteSpec object for messages to be written when the program halts due to an error.
err_halt_writespec: Any = None

# A MailSpec object for email to be sent when the program halts due to an error.
err_halt_email: Any = None

# A ScriptExecSpec object for a script to be executed when the program halts due to an error.
err_halt_exec: Any = None

# A WriteSpec object for messages to be written when the program halts due to user cancellation.
cancel_halt_writespec: Any = None

# A MailSpec object for email to be sent when the program halts due to user cancellation.
cancel_halt_mailspec: Any = None

# A ScriptExecSpec object for a script to be executed when the program halts due to user cancellation.
cancel_halt_exec: Any = None

# A stack of the CommandList objects currently in the queue to be executed.
commandliststack: list = []

# A dictionary of CommandList objects (ordinarily created by BEGIN/END SCRIPT metacommands).
savedscripts: dict = {}

# A stack of CommandList objects used when compiling the statements within a loop.
loopcommandstack: list = []

# A global flag to indicate that commands should be compiled into the topmost entry
# in the loopcommandstack rather than executed.
compiling_loop: bool = False

# Compiled regex for END LOOP metacommand, which is immediate.
endloop_rx = re.compile(r"^\s*END\s+LOOP\s*$", re.I)

# Compiled regex for *start of* LOOP metacommand, for testing while compiling commands within a loop.
loop_rx = re.compile(r"\s*LOOP\s+", re.I)

# Nesting counter, to ensure loops are only ended when nesting level is zero.
loop_nest_level: int = 0

# A count of all of the commands run.
cmds_run: int = 0

# Pattern for deferred substitution, e.g.: "!{somevar}!"
defer_rx = re.compile(r"(!{([$@&~#]?[a-z0-9_]+)}!)", re.I)

# The string type (str in Python 3).
stringtypes: type = str

# The execution log object; set at startup.
exec_log: Any = None

# The substitution variable set; set at startup.
subvars: Any = None

# The program execution status tracker; set at startup.
status: Any = None

# ---------------------------------------------------------------------------
# Runtime objects — initialized in main() to avoid circular imports at load time.
# ---------------------------------------------------------------------------

# Stack-based conditional state (IfLevels instance).
if_stack: Any = None

# Global counter variables (CounterVars instance).
counters: Any = None

# Elapsed-time tracker (Timer instance).
timer: Any = None

# Redirectable output (WriteHooks instance).
output: Any = None

# Database connection pool (DatabasePool instance).
dbs: Any = None

# Temporary file manager (TempFileMgr instance).
tempfiles: Any = None

# Export metadata tracker (ExportMetadata instance).
export_metadata: Any = None

# Metacommand dispatch table (MetaCommandList instance).
metacommandlist: Any = None

# Conditional predicate dispatch table (MetaCommandList instance).
conditionallist: Any = None

# Asynchronous file-writer subprocess (FileWriter instance).
filewriter: Any = None

# GUI console object.
gui_console: Any = None

# Queue and thread used to communicate with the GUI manager.
gui_manager_queue: Any = None
gui_manager_thread: Any = None

# ---------------------------------------------------------------------------
# Version numbers (parsed from package __version__)
# ---------------------------------------------------------------------------

try:
    from execsql import __version__ as _pkg_version

    _vparts = _pkg_version.split(".")
    primary_vno: int = int(_vparts[0]) if len(_vparts) > 0 else 0
    secondary_vno: int = int(_vparts[1]) if len(_vparts) > 1 else 0
    tertiary_vno: int = int(_vparts[2]) if len(_vparts) > 2 else 0
except Exception:
    primary_vno = 1
    secondary_vno = 130
    tertiary_vno = 1

# ---------------------------------------------------------------------------
# Utility functions defined directly here to avoid circular imports.
# ---------------------------------------------------------------------------


def xcmd_test(teststr: str) -> bool:
    """Evaluate a conditional test string and return a boolean result."""
    from execsql.parser import CondParser
    from execsql.exceptions import ErrInfo

    result = CondParser(teststr).parse().eval()
    if result is not None:
        return result
    raise ErrInfo(type="cmd", command_text=teststr, other_msg="Unrecognized conditional")


def endloop() -> None:
    """Complete the current loop being compiled and push it onto the command stack."""
    from execsql.exceptions import ErrInfo

    global compiling_loop
    if len(loopcommandstack) == 0:
        raise ErrInfo("error", other_msg="END LOOP metacommand without a matching preceding LOOP metacommand.")
    compiling_loop = False
    commandliststack.append(loopcommandstack[-1])
    loopcommandstack.pop()


# ---------------------------------------------------------------------------
# Deferred re-exports
# Placed at the bottom so that circular imports resolve correctly:
# all state variables above are defined before any module below is loaded.
# Modules that `import execsql.state as _state` will receive a partial
# module (containing only the variables above) if they are themselves
# imported during this block — which is safe because those modules only
# access _state.X inside function/method bodies, never at class-definition time.
# ---------------------------------------------------------------------------

# Exceptions and parser — always safe (exceptions.py / parser.py import state
# but only use _state inside function bodies, never at module level after init).
from execsql.exceptions import ErrInfo  # noqa: E402
from execsql.parser import CondParser, NumericParser  # noqa: E402

# script.py defines the core execution data structures.
from execsql.script import (  # noqa: E402
    IfLevels,
    CounterVars,
    SubVarSet,
    LocalSubVarSet,
    ScriptArgSubVarSet,
    MetaCommand,
    MetaCommandList,
    SqlStmt,
    MetacommandStmt,
    ScriptCmd,
    CommandList,
    CommandListWhileLoop,
    CommandListUntilLoop,
    ScriptFile,
    ScriptExecSpec,
    set_system_vars,
    substitute_vars,
    runscripts,
    current_script_line,
    read_sqlfile,
)

# xcmd_test also lives in conditions.py; keep the version defined above
# (identical logic) so that state.xcmd_test works without an extra import.
# write_warning / exit_now / fatal_error / exception_desc
from execsql.utils.errors import (  # noqa: E402
    exception_desc,
    exit_now,
    fatal_error,
    file_size_date,
    write_warning,
)

# File-I/O helpers
from execsql.utils.fileio import (  # noqa: E402
    check_dir,
    EncodedFile,
    FileWriter,
    Logger,
    TempFileMgr,
    filewriter_write,
    filewriter_close,
    filewriter_close_all_after_write,
    filewriter_open_as_new,
    filewriter_end,
)

# String utilities
from execsql.utils.strings import (  # noqa: E402
    clean_words,
    fold_words,
    is_doublequoted,
    unquoted,
    unquoted2,
    get_subvarset,
)

# Other utilities
from execsql.utils.crypto import Encrypt  # noqa: E402
from execsql.utils.timer import Timer  # noqa: E402
from execsql.utils.mail import Mailer, MailSpec  # noqa: E402
from execsql.utils.datetime import parse_datetime  # noqa: E402
from execsql.utils.auth import get_password  # noqa: E402

# Data models
from execsql.models import DataTable  # noqa: E402
from execsql.types import DT_Boolean, DT_Date, DT_Timestamp, DT_TimestampTZ  # noqa: E402

# Export infrastructure
from execsql.exporters.base import ExportRecord, ExportMetadata, WriteSpec  # noqa: E402
from execsql.exporters.pretty import prettyprint_query, prettyprint_rowset  # noqa: E402
from execsql.exporters.templates import report_query  # noqa: E402
from execsql.exporters.delimited import write_delimited_file, CsvFile  # noqa: E402
from execsql.exporters.html import write_query_to_html, write_query_to_cgi_html  # noqa: E402
from execsql.exporters.json import write_query_to_json, write_query_to_json_ts  # noqa: E402
from execsql.exporters.xml import write_query_to_xml  # noqa: E402
from execsql.exporters.ods import write_query_to_ods, write_queries_to_ods, OdsFile  # noqa: E402
from execsql.exporters.sqlite import write_query_to_sqlite  # noqa: E402
from execsql.exporters.duckdb import write_query_to_duckdb  # noqa: E402
from execsql.exporters.latex import write_query_to_latex  # noqa: E402
from execsql.exporters.feather import write_query_to_feather, write_query_to_hdf5  # noqa: E402
from execsql.exporters.raw import write_query_raw, write_query_b64 as write_query_b  # noqa: E402
from execsql.exporters.values import write_query_to_values  # noqa: E402
from execsql.exporters.xls import XlsFile, XlsxFile  # noqa: E402

# Alias for HDF — upstream used write_query_to_hdf
write_query_to_hdf = write_query_to_hdf5

# Import infrastructure
from execsql.importers.csv import importtable, importfile  # noqa: E402
from execsql.importers.ods import ods_data, importods  # noqa: E402
from execsql.importers.xls import xls_data, importxls  # noqa: E402
from execsql.importers.feather import import_feather, import_parquet  # noqa: E402
from execsql.importers.base import import_data_table  # noqa: E402

# Database layer
from execsql.db.base import DatabasePool  # noqa: E402
from execsql.db.postgres import PostgresDatabase  # noqa: E402
from execsql.db.sqlite import SQLiteDatabase  # noqa: E402
from execsql.db.mysql import MySQLDatabase  # noqa: E402
from execsql.db.duckdb import DuckDBDatabase  # noqa: E402
from execsql.db.firebird import FirebirdDatabase  # noqa: E402
from execsql.db.oracle import OracleDatabase  # noqa: E402
from execsql.db.access import AccessDatabase  # noqa: E402
from execsql.db.sqlserver import SqlServerDatabase  # noqa: E402
from execsql.db.dsn import DsnDatabase  # noqa: E402

# Database type descriptors
from execsql.types import dbt_postgres, dbt_firebird  # noqa: E402

# GUI layer — pluggable backends: Textual (TUI), Tkinter (desktop), Console
from execsql.utils.gui import (  # noqa: E402
    gui_console_isrunning,
    enable_gui,
    gui_console_on,
    gui_console_off,
    gui_console_hide,
    gui_console_show,
    gui_console_progress,
    gui_console_save,
    gui_console_status,
    gui_console_wait_user,
    gui_console_height,
    gui_console_width,
    gui_connect,
    gui_credentials,
    GuiSpec,
    ConsoleUIError,
    ActionSpec,
    EntrySpec,
    GUI_HALT,
    GUI_MSG,
    GUI_PAUSE,
    GUI_DISPLAY,
    GUI_ENTRY,
    GUI_COMPARE,
    GUI_SELECTROWS,
    GUI_SELECTSUB,
    GUI_ACTION,
    GUI_MAP,
    GUI_OPENFILE,
    GUI_SAVEFILE,
    GUI_DIRECTORY,
    QUERY_CONSOLE,
    GUI_CREDENTIALS,
    GUI_CONNECT,
    get_yn,
    get_yn_win,
    pause,
    pause_win,
)
