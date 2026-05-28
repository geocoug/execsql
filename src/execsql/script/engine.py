from __future__ import annotations

"""Script execution engine for execsql.

Holds the metacommand dispatch primitives, the statement data types
consumed by the AST executor, and the substitution-variable helpers
shared by the parser and executor. Script parsing and tree-walking
live in :mod:`execsql.script.parser` and
:mod:`execsql.script.executor` respectively.

Classes:
- :class:`MetaCommand` — one entry in the metacommand dispatch table.
- :class:`MetaCommandList` — ordered list of :class:`MetaCommand` entries with a keyword index.
- :class:`SqlStmt` — wraps a single SQL string for execution.
- :class:`MetacommandStmt` — wraps a metacommand line for dispatch.
- :class:`ScriptCmd` — pairs a statement with its source-file location.
- :class:`ScriptExecSpec` — specification for deferred script execution.

Functions:
- :func:`set_system_vars` — populates built-in ``$VARNAME`` system variables (calls the static + dynamic helpers).
- :func:`set_static_system_vars` / :func:`set_dynamic_system_vars` — refresh the half-static / per-statement system variables independently.
- :func:`substitute_vars` — performs ``!!$VAR!!`` / ``!'!var!'!`` / ``!"!var!"!`` / ``!{$var}!`` expansion.
- :func:`current_script_line` — returns the ``(file, line_no)`` of the currently executing command.
"""

import datetime
import os
import re
import uuid
from pathlib import Path
from typing import Any

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.script.variables import SubVarSet
from execsql.utils.errors import exception_desc

__all__ = [
    "MetaCommand",
    "MetaCommandList",
    "SqlStmt",
    "MetacommandStmt",
    "ScriptCmd",
    "ScriptExecSpec",
    "set_system_vars",
    "substitute_vars",
    "current_script_line",
]


# ---------------------------------------------------------------------------
# MetaCommand / MetaCommandList
# ---------------------------------------------------------------------------


class MetaCommand:
    """A single entry in the metacommand dispatch table.

    Holds a compiled regex, a handler function, and execution-control flags.
    Call :meth:`run` with a raw command string to attempt a match and invoke
    the handler.
    """

    # A compiled metacommand that can be run if it matches a metacommand command string.
    def __init__(
        self,
        rx: Any,
        exec_func: Any,
        description: str | None = None,
        set_error_flag: bool = True,
        category: str | None = None,
    ) -> None:
        self.rx = rx
        self.exec_fn = exec_func
        self.description = description
        self.set_error_flag = set_error_flag
        self.category = category
        self.hitcount = 0

    def __repr__(self) -> str:
        return f"MetaCommand({self.rx.pattern!r}, {self.exec_fn!r}, {self.description!r})"

    def run(self, cmd_str: str) -> tuple:
        """Match *cmd_str* against this entry's regex and, if it matches, invoke the handler.

        Returns ``(True, return_value)`` on a match, ``(False, None)`` otherwise.
        """
        # Runs the metacommand if the command string matches the regex.
        m = self.rx.match(cmd_str.strip())
        if m:
            cmdargs = m.groupdict()
            cmdargs["metacommandline"] = cmd_str
            er = None
            try:
                rv = self.exec_fn(**cmdargs)
            except SystemExit:
                raise
            except ErrInfo as errinf:
                er = errinf
            except Exception:
                er = ErrInfo("cmd", command_text=cmd_str, exception_msg=exception_desc())
            if er:
                if _state.status.halt_on_metacommand_err:
                    from execsql.utils.errors import exit_now

                    exit_now(1, er)
                if self.set_error_flag:
                    _state.status.metacommand_error = True
                    return True, None
            else:
                if self.set_error_flag:
                    _state.status.metacommand_error = False
                self.hitcount += 1
                return True, rv
        return False, None


class MetaCommandList:
    """Ordered list of :class:`MetaCommand` entries with keyword-indexed dispatch.

    Commands are stored with the most-recently-added entry first, matching
    the original linked-list prepend semantics.  A keyword index
    (``_by_keyword``) groups entries by their leading keyword so that
    ``eval()`` and ``get_match()`` test only the small subset of regexes
    that could possibly match, reducing dispatch from O(N) to O(K) where
    K is the number of patterns sharing the same leading keyword (typically
    1–5 vs. 205 total).
    """

    # Regex to extract the leading keyword from a metacommand regex pattern.
    # Handles ^\s*KEYWORD, ^KEYWORD, and ^\s*(?:PREFIX\s+)?KEYWORD.
    _KEYWORD_RX = re.compile(
        r"^\^"
        r"(?:\\s\*)?(?:\(\?:[^)]+\))?(?:\\s\+)?"
        r"(?:\\s\*)?"
        r"([A-Z_]+)",
    )

    def __init__(self) -> None:
        self._commands: list[MetaCommand] = []
        self._by_keyword: dict[str, list[MetaCommand]] = {}
        self._unkeyed: list[MetaCommand] = []

    def __iter__(self) -> Any:
        return iter(self._commands)

    @staticmethod
    def _extract_keyword(cmd_str: str) -> str | None:
        """Extract the leading keyword from a metacommand string."""
        word = cmd_str.strip().split(None, 1)
        return word[0].upper() if word else None

    def _index_command(self, mc: MetaCommand, rx_pattern: str) -> None:
        """Add *mc* to the keyword index based on its regex pattern."""
        m = self._KEYWORD_RX.match(rx_pattern)
        if m:
            kw = m.group(1)
            self._by_keyword.setdefault(kw, []).insert(0, mc)
        else:
            self._unkeyed.insert(0, mc)

    def add(
        self,
        matching_regexes: Any,
        exec_func: Any,
        description: str | None = None,
        set_error_flag: bool = True,
        category: str | None = None,
    ) -> None:
        """Register one or more regex patterns as a new :class:`MetaCommand` entry.

        *matching_regexes* may be a single pattern string or a list/tuple of
        patterns; each compiles into a separate :class:`MetaCommand` prepended to
        the dispatch list so that later registrations take priority.
        """
        if isinstance(matching_regexes, (tuple, list)):
            raw_patterns = list(matching_regexes)
            regexes = [re.compile(rx, re.I) for rx in raw_patterns]
        else:
            raw_patterns = [matching_regexes]
            regexes = [re.compile(matching_regexes, re.I)]
        for rx, raw in zip(regexes, raw_patterns):
            mc = MetaCommand(
                rx,
                exec_func,
                description,
                set_error_flag,
                category,
            )
            # Prepend to preserve "last registered, first checked" ordering.
            self._commands.insert(0, mc)
            self._index_command(mc, raw)

    def _candidates(self, cmd_str: str) -> list[MetaCommand]:
        """Return the subset of commands whose keyword matches *cmd_str*.

        Falls back to the full command list if no keyword match is found.
        """
        kw = self._extract_keyword(cmd_str)
        if kw and kw in self._by_keyword:
            # Keyword-matched entries plus any unkeyed entries that could match anything.
            return self._by_keyword[kw] + self._unkeyed
        return self._commands

    def keywords_by_category(self) -> dict[str, list[str]]:
        """Return ``{category: [keyword, ...]}`` from entries that have both.

        Used by ``--dump-keywords`` to introspect the dispatch table.
        """
        result: dict[str, list[str]] = {}
        for mc in self._commands:
            if mc.category and mc.description:
                kw_list = result.setdefault(mc.category, [])
                if mc.description not in kw_list:
                    kw_list.append(mc.description)
        return result

    def eval(self, cmd_str: str) -> tuple:
        """Evaluate *cmd_str* against the registered metacommands.

        Returns ``(True, return_value)`` if a matching command was found and
        run, ``(False, None)`` if no command matched.
        """
        for cmd in self._candidates(cmd_str):
            success, value = cmd.run(cmd_str)
            if success:
                return True, value
        return False, None

    def get_match(self, cmd: str) -> tuple | None:
        """Return ``(MetaCommand, re.Match)`` for the first entry matching *cmd*,
        or ``None`` if no entry matches.
        """
        stripped = cmd.strip()
        for node in self._candidates(stripped):
            m = node.rx.match(stripped)
            if m is not None:
                return (node, m)
        return None


# ---------------------------------------------------------------------------
# SqlStmt / MetacommandStmt
# ---------------------------------------------------------------------------


class SqlStmt:
    """A single SQL statement ready to be executed against the active database.

    Data class only — the legacy ``.run()`` method was removed when the AST
    executor became the sole engine.  SQL execution now goes through
    :func:`execsql.script.executor._exec_sql`.
    """

    def __init__(self, sql_statement: str) -> None:
        self.statement = re.sub(r"\s*;(\s*;\s*)+$", ";", sql_statement)

    def __repr__(self) -> str:
        return f"SqlStmt({self.statement})"

    def commandline(self) -> str:
        """Return the raw SQL statement text."""
        return self.statement


class MetacommandStmt:
    """A single execsql metacommand line.

    Data class only — the legacy ``.run()`` method was removed when the AST
    executor became the sole engine.  Metacommand dispatch now goes through
    :func:`execsql.script.executor._exec_metacommand`.
    """

    def __init__(self, metacommand_statement: str) -> None:
        self.statement = metacommand_statement

    def __repr__(self) -> str:
        return f"MetacommandStmt({self.statement})"

    def commandline(self) -> str:
        """Return the metacommand line in its canonical ``-- !x! ...`` form."""
        return "-- !x! " + self.statement


# ---------------------------------------------------------------------------
# ScriptCmd
# ---------------------------------------------------------------------------


class ScriptCmd:
    """A parsed script item: either a :class:`SqlStmt` or a :class:`MetacommandStmt`, with source location."""

    # A SQL script object that is either a SQL statement or a metacommand.
    def __init__(
        self,
        command_source_name: str,
        command_line_no: int,
        command_type: str,
        script_command: Any,
    ) -> None:
        self.source = command_source_name
        self.line_no = command_line_no
        self.command_type = command_type
        self.command = script_command
        # MIGRATION NOTE: differs from monolith (execsql.py) — source_dir and source_name are
        # resolved once at construction rather than on every statement execution.  For absolute
        # paths (the common case) the result is identical.  For relative paths the value is
        # anchored to the CWD at script-load time rather than at each statement's execution time;
        # the original per-statement resolve could yield inconsistent values across statements of
        # the same script if a CD metacommand ran between them.
        _p = Path(command_source_name)
        self.source_dir: str = str(_p.resolve().parent) + os.sep
        self.source_name: str = _p.name

    def __repr__(self) -> str:
        return f"ScriptCmd({self.source!r}, {self.line_no!r}, {self.command_type!r}, {repr(self.command)!r})"

    def current_script_line(self) -> tuple:
        return (self.source, self.line_no)

    def commandline(self) -> str:
        return self.command.statement if self.command_type == "sql" else "-- !x! " + self.command.statement


# ---------------------------------------------------------------------------
# ScriptExecSpec
# ---------------------------------------------------------------------------


class ScriptExecSpec:
    """Deferred execution specification for a named SCRIPT block.

    Stores the script ID, argument expression, and loop-type flags at
    construction time.  Used by ON ERROR_HALT / ON CANCEL_HALT EXECUTE
    SCRIPT handlers to capture the specification; actual execution is
    handled by the AST executor via :func:`_run_deferred_script`.
    """

    def __init__(self, **kwargs: Any) -> None:
        self.script_id = kwargs["script_id"].lower()
        if self.script_id not in _state.ast_scripts:
            raise ErrInfo("cmd", other_msg=f"There is no SCRIPT named {self.script_id}.")
        self.arg_exp = kwargs["argexp"]
        self.looptype = kwargs["looptype"].upper() if "looptype" in kwargs and kwargs["looptype"] is not None else None
        self.loopcond = kwargs.get("loopcond")


# ---------------------------------------------------------------------------
# Module-level functions
# ---------------------------------------------------------------------------


def set_static_system_vars(ctx: Any = None) -> None:
    """Set system substitution variables that only change on CONNECT or CHDIR.

    Called once before the execution loop.  These values are expensive to compute
    (filesystem syscalls, database pool lookups) but rarely change — only on
    ``CONNECT``, ``USE``, or ``CHDIR`` metacommands.  The ``runscripts()`` loop
    calls this once up front; metacommand handlers that change the connection or
    working directory should call it again afterward.

    Args:
        ctx: Optional :class:`RuntimeContext`.  When ``None``, falls through
            to the global ``_state`` module (legacy behavior).
    """
    import random

    _s = ctx if ctx is not None else _state
    cwd = str(Path(".").resolve())
    _s.subvars.add_substitution("$CURRENT_DIR", cwd)
    _s.subvars.add_substitution("$CURRENT_PATH", cwd + os.sep)
    _s.subvars.add_substitution("$CURRENT_ALIAS", _s.dbs.current_alias())
    db = _s.dbs.current()
    _s.subvars.add_substitution("$DB_USER", db.user if db.user else "")
    _s.subvars.add_substitution(
        "$DB_SERVER",
        db.server_name if db.server_name else "",
    )
    _s.subvars.add_substitution("$DB_NAME", db.db_name)
    _s.subvars.add_substitution("$DB_NEED_PWD", "TRUE" if db.need_passwd else "FALSE")
    _s.subvars.add_substitution("$CURRENT_DBMS", db.type.dbms_id)
    _s.subvars.add_substitution("$CURRENT_DATABASE", db.name())
    _s.subvars.add_substitution("$VERSION1", str(_state.primary_vno))
    _s.subvars.add_substitution("$VERSION2", str(_state.secondary_vno))
    _s.subvars.add_substitution("$VERSION3", str(_state.tertiary_vno))
    # Register lazy providers for $RANDOM and $UUID — computed only when referenced.
    _s.subvars.register_lazy("$random", lambda: str(random.random()))
    _s.subvars.register_lazy("$uuid", lambda: str(uuid.uuid4()))


def set_dynamic_system_vars(ctx: Any = None) -> None:
    """Refresh system substitution variables that change every statement.

    Called once per statement in the execution loop.  Includes cheap boolean-to-string
    conversions for halt states and autocommit (which can change on any CONFIG or
    AUTOCOMMIT metacommand) plus ``$TIMER`` and lazy-variable cache reset.

    Args:
        ctx: Optional :class:`RuntimeContext`.  When ``None``, falls through
            to the global ``_state`` module (legacy behavior).
    """
    _s = ctx if ctx is not None else _state
    # Halt/config state vars — cheap to set, can change on any CONFIG metacommand.
    _s.subvars.add_substitution("$CANCEL_HALT_STATE", "ON" if _s.status.cancel_halt else "OFF")
    _s.subvars.add_substitution("$ERROR_HALT_STATE", "ON" if _s.status.halt_on_err else "OFF")
    _s.subvars.add_substitution(
        "$METACOMMAND_ERROR_HALT_STATE",
        "ON" if _s.status.halt_on_metacommand_err else "OFF",
    )
    _s.subvars.add_substitution(
        "$CONSOLE_WAIT_WHEN_ERROR_HALT_STATE",
        "ON" if _s.conf.gui_wait_on_error_halt else "OFF",
    )
    _s.subvars.add_substitution("$CONSOLE_WAIT_WHEN_DONE_STATE", "ON" if _s.conf.gui_wait_on_exit else "OFF")
    db = _s.dbs.current()
    _s.subvars.add_substitution("$AUTOCOMMIT_STATE", "ON" if db.autocommit else "OFF")
    # $CURRENT_TIME is set per-statement in executor._set_command_vars() for accuracy.
    _s.subvars.add_substitution("$TIMER", str(datetime.timedelta(seconds=_s.timer.elapsed())))
    _s.subvars.clear_lazy_cache()


def set_system_vars(ctx: Any = None) -> None:
    """Refresh all built-in system substitution variables.

    Convenience wrapper that calls both :func:`set_static_system_vars` and
    :func:`set_dynamic_system_vars`.  Retained for backward compatibility with
    tests and any external callers.
    """
    set_static_system_vars(ctx)
    set_dynamic_system_vars(ctx)


_MAX_SUBSTITUTION_DEPTH = 100
# B17/F013: output-byte ceiling for substitute_vars. The depth cap
# above stops cyclic references (a → !!b!!, b → !!a!!) but does not
# stop exponential expansion: a single variable referencing the same
# other variable N times grows ``2^N`` per iteration without ever
# looping. Track the rendered length and abort when it crosses
# _MAX_SUBSTITUTION_BYTES (default 10 MB — well above any legitimate
# SQL statement, comfortably below a memory-pressure failure mode).
_MAX_SUBSTITUTION_BYTES = 10 * 1024 * 1024


def substitute_vars(command_str: str, localvars: SubVarSet | None = None, ctx: Any = None) -> str:
    """Expand all ``!!$VAR!!`` tokens in *command_str*, merging *localvars* when provided.

    Args:
        command_str: The string containing ``!!VAR!!`` tokens to expand.
        localvars: Optional local variable overlay to merge with globals.
        ctx: Optional :class:`RuntimeContext`.  When ``None``, falls through
            to the global ``_state`` module (legacy behavior).

    Raises:
        ErrInfo: when the iteration count exceeds
            :data:`_MAX_SUBSTITUTION_DEPTH` (cyclic reference) OR the
            expanded output exceeds :data:`_MAX_SUBSTITUTION_BYTES`
            (exponential expansion bomb).
    """
    _s = ctx if ctx is not None else _state
    if localvars is not None:
        subs = _s.subvars.merge(localvars)
    else:
        subs = _s.subvars
    # Allow runtime override of the byte cap via conf. None / missing
    # → use the engine default (back-compat with users who legitimately
    # render multi-MB SQL through substitution).
    conf_max = getattr(_s.conf, "max_substitution_bytes", None)
    max_bytes = conf_max if conf_max is not None else _MAX_SUBSTITUTION_BYTES
    cmdstr = command_str
    subs_made = True
    iterations = 0
    while subs_made:
        subs_made = False
        cmdstr, subs_made = subs.substitute_all(cmdstr)
        cmdstr, any_subbed = _s.counters.substitute_all(cmdstr)
        subs_made = subs_made or any_subbed
        iterations += 1
        # Only enforce the byte cap when expansion ACTUALLY happened
        # this iteration. A user passing a large pre-existing literal
        # with no !!var!! tokens shouldn't be rejected — the cap
        # targets expansion-bomb growth, not literal input size.
        if subs_made and len(cmdstr) > max_bytes:
            raise ErrInfo(
                type="error",
                other_msg=(
                    f"Substitution variable expansion exceeded {max_bytes} bytes "
                    f"(possible exponential expansion bomb) while expanding: "
                    f"{command_str[:200]}"
                ),
            )
        if iterations >= _MAX_SUBSTITUTION_DEPTH:
            raise ErrInfo(
                type="error",
                other_msg=(
                    f"Substitution variable cycle detected: exceeded {_MAX_SUBSTITUTION_DEPTH} "
                    f"iterations while expanding variables in: {command_str[:200]}"
                ),
            )
    m = _state.defer_rx.findall(cmdstr)
    # Substitute any deferred substitution variables with regular substitution var flags.
    if m is not None:
        for dv in m:
            rep = "!!" + dv[1] + "!!"
            cmdstr = cmdstr.replace(dv[0], rep)
    return cmdstr


def current_script_line() -> tuple:
    """Return ``(source_name, line_number)`` for the command currently executing.

    Reads from ``_state.last_command``, which the AST executor updates on
    every statement via the ``_FakeScriptCmd`` shim.  Returns ``("", 0)``
    when nothing has executed yet (e.g. during early initialization errors).
    """
    last = getattr(_state, "last_command", None)
    if last is None:
        return ("", 0)
    return (getattr(last, "source", ""), getattr(last, "line_no", 0))
