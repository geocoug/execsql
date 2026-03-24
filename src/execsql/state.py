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

All re-exports have been removed. Each module now imports directly from
its source module rather than accessing names via ``_state``.
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
    import execsql.parser as _parser
    import execsql.exceptions as _exc

    result = _parser.CondParser(teststr).parse().eval()
    if result is not None:
        return result
    raise _exc.ErrInfo(type="cmd", command_text=teststr, other_msg="Unrecognized conditional")


def endloop() -> None:
    """Complete the current loop being compiled and push it onto the command stack."""
    import execsql.exceptions as _exc

    global compiling_loop
    if len(loopcommandstack) == 0:
        raise _exc.ErrInfo("error", other_msg="END LOOP metacommand without a matching preceding LOOP metacommand.")
    compiling_loop = False
    commandliststack.append(loopcommandstack[-1])
    loopcommandstack.pop()


# ---------------------------------------------------------------------------
# Test-support utilities
# ---------------------------------------------------------------------------


def reset() -> None:
    """Reset all module-level state to initial values.

    Intended for use in tests. Clears mutable containers, resets counters,
    and sets all lazy singletons back to ``None`` so that each test starts
    from a clean slate.
    """
    global compiling_loop, loop_nest_level, cmds_run
    global conf, last_command, upass
    global err_halt_writespec, err_halt_email, err_halt_exec
    global cancel_halt_writespec, cancel_halt_mailspec, cancel_halt_exec
    global exec_log, subvars, status, if_stack, counters, timer
    global output, dbs, tempfiles, export_metadata
    global metacommandlist, conditionallist, filewriter
    global gui_console, gui_manager_queue, gui_manager_thread

    # Mutable containers — clear in-place (no rebind needed)
    commandliststack.clear()
    loopcommandstack.clear()
    savedscripts.clear()

    # Scalar flags and counters
    compiling_loop = False
    loop_nest_level = 0
    cmds_run = 0

    # Lazy singletons — reset to None
    conf = None
    last_command = None
    upass = None
    err_halt_writespec = None
    err_halt_email = None
    err_halt_exec = None
    cancel_halt_writespec = None
    cancel_halt_mailspec = None
    cancel_halt_exec = None
    exec_log = None
    subvars = None
    status = None
    if_stack = None
    counters = None
    timer = None
    output = None
    dbs = None
    tempfiles = None
    export_metadata = None
    metacommandlist = None
    conditionallist = None
    # filewriter is a multiprocessing.Process managed by atexit — do NOT null
    # it here.  Nulling it while the subprocess is alive creates two competing
    # consumers on the shared fw_input queue, causing test-to-test races.
    gui_console = None
    gui_manager_queue = None
    gui_manager_thread = None


def initialize(
    config: "ConfigData",
    dispatch_table: object,
    conditional_table: object,
) -> None:
    """Initialize the shared runtime singletons for a new execsql run.

    Called once from :func:`execsql.cli._run` after configuration has been
    loaded.  Consolidates object construction in one place so that the
    sequence is documented, testable, and not scattered across the CLI
    entry-point.

    Args:
        config: A fully-populated :class:`execsql.config.ConfigData` instance.
        dispatch_table: The metacommand dispatch table
            (``execsql.metacommands.DISPATCH_TABLE``).
        conditional_table: The conditional-predicate dispatch table
            (``execsql.metacommands.conditions.CONDITIONAL_TABLE``).

    Note:
        ``subvars``, ``status``, ``output``, ``filewriter``, and ``exec_log``
        are **not** set here because they require CLI-specific arguments
        (script path, subprocess queues, local class definitions).  Those are
        assigned directly in ``_run()`` before and after this call.
    """
    global conf, if_stack, counters, timer, dbs, tempfiles
    global export_metadata, metacommandlist, conditionallist

    # These names are re-exported at the bottom of this module (after this
    # function definition), so they are guaranteed to be available by the time
    # initialize() is called from cli._run().  Using the module-level names
    # avoids F811 "redefinition of unused name" from local imports.
    import execsql.script as _script
    import execsql.utils.timer as _timer_mod
    import execsql.db.base as _db_base
    import execsql.utils.fileio as _fileio_mod
    import execsql.exporters.base as _exporters_base

    conf = config
    if_stack = _script.IfLevels()
    counters = _script.CounterVars()
    timer = _timer_mod.Timer()
    dbs = _db_base.DatabasePool()
    tempfiles = _fileio_mod.TempFileMgr()
    export_metadata = _exporters_base.ExportMetadata()
    metacommandlist = dispatch_table
    conditionallist = conditional_table
