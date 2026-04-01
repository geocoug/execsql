from __future__ import annotations

"""
Module-level global runtime state for execsql.

All mutable singletons and global variables that need to be shared across
the entire codebase are declared here.  Other modules do::

    import execsql.state as _state

and then access attributes (``_state.conf``, ``_state.subvars``, etc.)
inside function/method bodies — never at class-definition time — to avoid
circular-import issues at load time.

Internally, all mutable state lives on a :class:`RuntimeContext` instance
(``_ctx``).  The module's ``__class__`` is swapped to a custom
:class:`types.ModuleType` subclass that transparently proxies attribute
reads and writes to the active context.  This means:

- External code continues to use ``_state.conf``, ``_state.subvars = ...``,
  etc. with zero changes.
- Functions *within* this module use ``_ctx.conf``, ``_ctx.subvars``, etc.
  directly, because Python's ``LOAD_GLOBAL`` / ``STORE_GLOBAL`` bytecodes
  access ``__dict__`` directly and do not trigger ``__getattr__`` /
  ``__setattr__`` on the module class.

Use :func:`get_context` / :func:`set_context` to obtain or replace the
active context programmatically.
"""

import re
import sys
import types
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import multiprocessing as _mp
    import threading as _threading

    from execsql.config import ConfigData, StatObj, WriteHooks
    from execsql.db.base import DatabasePool
    from execsql.exporters.base import ExportMetadata, WriteSpec
    from execsql.script import (
        CommandList,
        CounterVars,
        IfLevels,
        MetaCommandList,
        ScriptCmd,
        ScriptExecSpec,
        SubVarSet,
    )
    from execsql.utils.fileio import FileWriter, Logger, TempFileMgr
    from execsql.utils.mail import MailSpec
    from execsql.utils.timer import Timer

__all__ = [
    # Configuration / encoding
    "conf",
    "logfile_encoding",
    # Runtime state
    "last_command",
    "upass",
    "varlike",
    "err_halt_writespec",
    "err_halt_email",
    "err_halt_exec",
    "cancel_halt_writespec",
    "cancel_halt_mailspec",
    "cancel_halt_exec",
    "commandliststack",
    "savedscripts",
    "loopcommandstack",
    "compiling_loop",
    "endloop_rx",
    "loop_rx",
    "loop_nest_level",
    "cmds_run",
    "defer_rx",
    "stringtypes",
    "exec_log",
    "subvars",
    "status",
    # Lazy singletons
    "if_stack",
    "counters",
    "timer",
    "output",
    "dbs",
    "tempfiles",
    "export_metadata",
    "metacommandlist",
    "conditionallist",
    "filewriter",
    "gui_console",
    "gui_manager_queue",
    "gui_manager_thread",
    # Profiling
    "profile_data",
    # Version
    "primary_vno",
    "secondary_vno",
    "tertiary_vno",
    # Functions
    "xcmd_test",
    "endloop",
    "reset",
    "initialize",
    # New public API
    "RuntimeContext",
    "get_context",
    "set_context",
]

# ---------------------------------------------------------------------------
# Compile-time constants — immutable after module load, stay in __dict__
# ---------------------------------------------------------------------------

# A compiled regex to match prefixed regular expressions, used to check
# for unsubstituted variables.
varlike = re.compile(r"!![$@&~#]?\w+!!", re.I)

# Compiled regex for END LOOP metacommand, which is immediate.
endloop_rx = re.compile(r"^\s*END\s+LOOP\s*$", re.I)

# Compiled regex for *start of* LOOP metacommand, for testing while compiling
# commands within a loop.
loop_rx = re.compile(r"\s*LOOP\s+", re.I)

# Pattern for deferred substitution, e.g.: "!{somevar}!"
defer_rx = re.compile(r"(!{([$@&~#]?[a-z0-9_]+)}!)", re.I)

# The string type (str in Python 3).
stringtypes: type = str

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
    primary_vno = 0
    secondary_vno = 0
    tertiary_vno = 0


# ---------------------------------------------------------------------------
# RuntimeContext — holds all mutable state for a single execsql session
# ---------------------------------------------------------------------------

_CONTEXT_ATTRS: frozenset[str] = frozenset(
    {
        # Configuration
        "conf",
        "logfile_encoding",
        # Runtime flags
        "last_command",
        "upass",
        "err_halt_writespec",
        "err_halt_email",
        "err_halt_exec",
        "cancel_halt_writespec",
        "cancel_halt_mailspec",
        "cancel_halt_exec",
        # Execution stack
        "commandliststack",
        "savedscripts",
        "loopcommandstack",
        "compiling_loop",
        "loop_nest_level",
        "cmds_run",
        # I/O
        "exec_log",
        "subvars",
        "status",
        "output",
        "filewriter",
        # Lazy singletons
        "if_stack",
        "counters",
        "timer",
        "dbs",
        "tempfiles",
        "export_metadata",
        "metacommandlist",
        "conditionallist",
        # GUI
        "gui_console",
        "gui_manager_queue",
        "gui_manager_thread",
        # Profiling
        "profile_data",
    },
)


class RuntimeContext:
    """All mutable runtime state for a single execsql execution session.

    A fresh instance provides clean default values identical to the original
    module-level declarations.  Use :func:`get_context` to obtain the active
    instance, or :func:`set_context` to replace it.
    """

    __slots__ = (
        # Configuration
        "conf",
        "logfile_encoding",
        # Runtime flags
        "last_command",
        "upass",
        "err_halt_writespec",
        "err_halt_email",
        "err_halt_exec",
        "cancel_halt_writespec",
        "cancel_halt_mailspec",
        "cancel_halt_exec",
        # Execution stack
        "commandliststack",
        "savedscripts",
        "loopcommandstack",
        "compiling_loop",
        "loop_nest_level",
        "cmds_run",
        # I/O
        "exec_log",
        "subvars",
        "status",
        "output",
        "filewriter",
        # Lazy singletons
        "if_stack",
        "counters",
        "timer",
        "dbs",
        "tempfiles",
        "export_metadata",
        "metacommandlist",
        "conditionallist",
        # GUI
        "gui_console",
        "gui_manager_queue",
        "gui_manager_thread",
        # Profiling
        "profile_data",
    )

    def __init__(self) -> None:
        # Configuration
        self.conf: ConfigData | None = None
        self.logfile_encoding: str = "utf8"

        # Runtime flags
        self.last_command: ScriptCmd | None = None
        self.upass: str | None = None
        self.err_halt_writespec: WriteSpec | None = None
        self.err_halt_email: MailSpec | None = None
        self.err_halt_exec: ScriptExecSpec | None = None
        self.cancel_halt_writespec: WriteSpec | None = None
        self.cancel_halt_mailspec: MailSpec | None = None
        self.cancel_halt_exec: ScriptExecSpec | None = None

        # Execution stack
        self.commandliststack: list[CommandList] = []
        self.savedscripts: dict[str, CommandList] = {}
        self.loopcommandstack: list[CommandList] = []
        self.compiling_loop: bool = False
        self.loop_nest_level: int = 0
        self.cmds_run: int = 0

        # I/O
        self.exec_log: Logger | None = None
        self.subvars: SubVarSet | None = None
        self.status: StatObj | None = None
        self.output: WriteHooks | None = None
        self.filewriter: FileWriter | None = None

        # Lazy singletons
        self.if_stack: IfLevels | None = None
        self.counters: CounterVars | None = None
        self.timer: Timer | None = None
        self.dbs: DatabasePool | None = None
        self.tempfiles: TempFileMgr | None = None
        self.export_metadata: ExportMetadata | None = None
        self.metacommandlist: MetaCommandList | None = None
        self.conditionallist: MetaCommandList | None = None

        # GUI
        self.gui_console: Any = None
        self.gui_manager_queue: _mp.Queue | None = None
        self.gui_manager_thread: _threading.Thread | None = None

        # Profiling — None means profiling is disabled; a list means it is enabled.
        # Each entry: (source, line_no, command_type, elapsed_secs, command_text_preview)
        self.profile_data: list[tuple] | None = None


# ---------------------------------------------------------------------------
# Module proxy — transparently delegates context attr access to _ctx
# ---------------------------------------------------------------------------


class _StateModule(types.ModuleType):
    """Module subclass that proxies mutable state attributes to the active RuntimeContext."""

    def __getattr__(self, name: str) -> Any:
        if name in _CONTEXT_ATTRS:
            return getattr(self.__dict__["_ctx"], name)
        raise AttributeError(f"module {self.__name__!r} has no attribute {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _CONTEXT_ATTRS:
            setattr(self.__dict__["_ctx"], name, value)
        else:
            super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name in _CONTEXT_ATTRS:
            # Reset to the fresh-context default.  Needed for
            # unittest.mock.patch compatibility: patch checks
            # ``name in target.__dict__`` to decide whether to restore
            # via setattr (local) or delattr (non-local).  Since context
            # attrs live on _ctx, not __dict__, patch takes the delattr
            # path.  We reset to the default rather than truly deleting.
            _defaults = RuntimeContext()
            setattr(self.__dict__["_ctx"], name, getattr(_defaults, name))
        else:
            super().__delattr__(name)

    def __dir__(self) -> list[str]:
        return sorted(set(super().__dir__()) | _CONTEXT_ATTRS)


# ---------------------------------------------------------------------------
# Utility functions — use _ctx directly (LOAD_GLOBAL bypasses the proxy)
# ---------------------------------------------------------------------------


def xcmd_test(teststr: str) -> bool:
    """Evaluate a conditional test string and return a boolean result."""
    import execsql.exceptions as _exc
    import execsql.parser as _parser

    result = _parser.CondParser(teststr).parse().eval()
    if result is not None:
        return result
    raise _exc.ErrInfo(type="cmd", command_text=teststr, other_msg="Unrecognized conditional")


def endloop() -> None:
    """Complete the current loop being compiled and push it onto the command stack."""
    import execsql.exceptions as _exc

    if len(_ctx.loopcommandstack) == 0:
        raise _exc.ErrInfo("error", other_msg="END LOOP metacommand without a matching preceding LOOP metacommand.")
    _ctx.compiling_loop = False
    _ctx.commandliststack.append(_ctx.loopcommandstack[-1])
    _ctx.loopcommandstack.pop()


# ---------------------------------------------------------------------------
# Context management
# ---------------------------------------------------------------------------


def get_context() -> RuntimeContext:
    """Return the active :class:`RuntimeContext`."""
    return _ctx


def set_context(ctx: RuntimeContext) -> None:
    """Replace the active :class:`RuntimeContext`.

    Args:
        ctx: The new context to install.  All subsequent ``_state.foo``
            accesses will resolve against this instance.
    """
    global _ctx
    _ctx = ctx


# ---------------------------------------------------------------------------
# Initialization and reset
# ---------------------------------------------------------------------------


def reset() -> None:
    """Reset all mutable state to initial values.

    Intended for use in tests.  Creates a fresh :class:`RuntimeContext`,
    preserving only the ``filewriter`` subprocess (which is ``atexit``-managed
    and must not be discarded while alive).
    """
    global _ctx

    # Preserve filewriter — it's atexit-managed and must survive resets.
    old_fw = _ctx.filewriter

    # Close open database connections before discarding the pool.
    if _ctx.dbs is not None:
        try:
            _ctx.dbs.closeall()
        except Exception:
            pass

    _ctx = RuntimeContext()
    _ctx.filewriter = old_fw


def initialize(
    config: ConfigData,
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
    import execsql.db.base as _db_base
    import execsql.exporters.base as _exporters_base
    import execsql.script as _script
    import execsql.utils.fileio as _fileio_mod
    import execsql.utils.timer as _timer_mod

    _ctx.conf = config
    _ctx.if_stack = _script.IfLevels()
    _ctx.counters = _script.CounterVars()
    _ctx.timer = _timer_mod.Timer()
    _ctx.dbs = _db_base.DatabasePool()
    _ctx.tempfiles = _fileio_mod.TempFileMgr()
    _ctx.export_metadata = _exporters_base.ExportMetadata()
    _ctx.metacommandlist = dispatch_table
    _ctx.conditionallist = conditional_table


# ---------------------------------------------------------------------------
# Bootstrap — create the initial context and swap the module class
# ---------------------------------------------------------------------------

_ctx = RuntimeContext()
sys.modules[__name__].__class__ = _StateModule
