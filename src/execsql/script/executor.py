"""AST-based script executor for execsql.

Walks a :class:`~execsql.script.ast.Script` tree and executes each node,
replacing the flat ``CommandList.run_next()`` loop for scripts parsed via
the AST parser.

Design:
    - **The executor owns control flow.**  IF conditions, LOOP iteration,
      and BATCH boundaries are driven by the tree structure — no
      ``_state.if_stack`` or ``_state.compiling_loop`` needed.
    - **SQL and metacommands delegate to the existing runtime.**  SQL is
      executed via the current database connection; metacommands are
      dispatched through ``_state.metacommandlist.eval()``.  This means
      all 200+ metacommand handlers work unchanged.
    - **Variable substitution** uses the existing ``substitute_vars()``.
    - **_state is still used** for database connections, substitution
      variables, output, logging, config, etc.  The Phase 2 refactor
      (instance-based RuntimeContext) will replace this.

Usage::

    from execsql.script.executor import execute
    from execsql.script.parser import parse_script

    tree = parse_script("pipeline.sql")
    execute(tree)
"""

from __future__ import annotations

import datetime
import os
import re
import time as _time
from pathlib import Path
from typing import Any

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.script.ast import (
    BatchBlock,
    ConditionModifier,
    IfBlock,
    IncludeDirective,
    LoopBlock,
    MetaCommandStatement,
    Node,
    Script,
    ScriptBlock,
    SqlBlock,
    SqlStatement,
)
from execsql.script.engine import substitute_vars
from execsql.script.variables import SubVarSet
from execsql.utils.errors import exception_desc

__all__ = ["execute"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Regex for deferred variable conversion: !{$VAR}! → !!$VAR!!
_DEFER_RX = re.compile(r"!\{([$@&~#+]?\w+)\}!")


def _convert_deferred_vars(text: str) -> str:
    """Convert deferred substitution variables to regular ones.

    In loop bodies, ``!{$VAR}!`` is converted to ``!!$VAR!!`` so that
    variables are re-evaluated on each iteration instead of being captured
    once at loop entry.
    """
    return _DEFER_RX.sub(r"!!\1!!", text)


def _eval_condition(condition: str, modifiers: list[ConditionModifier] | None = None) -> bool:
    """Evaluate a condition string with optional ANDIF/ORIF modifiers.

    The condition is first expanded via ``substitute_vars()``, then parsed
    and evaluated via ``_state.xcmd_test()``.
    """
    expanded = substitute_vars(condition)
    result = _state.xcmd_test(expanded)

    if modifiers:
        for mod in modifiers:
            mod_expanded = substitute_vars(mod.condition)
            mod_result = _state.xcmd_test(mod_expanded)
            if mod.kind == "AND":
                result = result and mod_result
            else:  # OR
                result = result or mod_result

    return result


def _set_command_vars(source: str, line_no: int) -> None:
    """Set per-command system variables (current script, line, time)."""
    now = datetime.datetime.now()
    _state.subvars.add_substitution("$CURRENT_TIME", now.strftime("%Y-%m-%d %H:%M"))
    _state.subvars.add_substitution("$CURRENT_DATE", now.strftime("%Y-%m-%d"))
    utcnow = datetime.datetime.now(tz=datetime.timezone.utc)
    _state.subvars.add_substitution("$CURRENT_TIME_UTC", utcnow.strftime("%Y-%m-%d %H:%M"))
    _p = Path(source)
    _state.subvars.add_substitution("$CURRENT_SCRIPT", source)
    _state.subvars.add_substitution("$CURRENT_SCRIPT_PATH", str(_p.resolve().parent) + os.sep)
    _state.subvars.add_substitution("$CURRENT_SCRIPT_NAME", _p.name)
    _state.subvars.add_substitution("$CURRENT_SCRIPT_LINE", str(line_no))
    _state.subvars.add_substitution("$SCRIPT_LINE", str(line_no))


# ---------------------------------------------------------------------------
# SQL execution (bypasses SqlStmt.run's if_stack check)
# ---------------------------------------------------------------------------


def _exec_sql(
    text: str,
    source: str,
    line_no: int,
    localvars: SubVarSet | None = None,
    commit: bool = True,
) -> None:
    """Execute a SQL statement against the current database.

    This replicates ``SqlStmt.run()`` but without the ``if_stack.all_true()``
    gate — the AST executor handles control flow via tree structure.
    """
    _state.status.sql_error = False
    if _state.status.batch.in_batch():
        _state.status.batch.using_db(_state.dbs.current())
    cmd = substitute_vars(text, localvars)
    if _state.varlike.search(cmd):
        _state.output.write(
            f"Warning: There is a potential un-substituted variable in the command\n     {cmd}\n",
        )
    e = None
    try:
        db = _state.dbs.current()
        if _state.conf.log_sql and _state.exec_log:
            _state.exec_log.log_sql_query(cmd, db.name(), line_no)
        db.execute(cmd)
        if commit:
            db.commit()
    except ErrInfo as errinfo:
        e = errinfo
    except SystemExit:
        raise
    except Exception:
        e = ErrInfo(type="exception", exception_msg=exception_desc())
    if e:
        from execsql.utils.errors import stamp_errinfo

        stamp_errinfo(e)
        _state.subvars.add_substitution("$LAST_ERROR", cmd)
        _state.subvars.add_substitution("$ERROR_MESSAGE", e.errmsg())
        _state.status.sql_error = True
        if _state.exec_log is not None:
            _state.exec_log.log_status_info(f"SQL error: {e.errmsg()}")
        if _state.status.halt_on_err:
            from execsql.utils.errors import exit_now

            exit_now(1, e)
        return
    _state.subvars.add_substitution("$LAST_SQL", cmd)


# ---------------------------------------------------------------------------
# Metacommand execution (bypasses MetacommandStmt.run's if_stack check)
# ---------------------------------------------------------------------------


def _exec_metacommand(
    command: str,
    source: str,
    line_no: int,
    localvars: SubVarSet | None = None,
) -> Any:
    """Dispatch a metacommand through the dispatch table.

    This replicates ``MetacommandStmt.run()`` but without the
    ``if_stack.all_true()`` gate.
    """
    cmd = substitute_vars(command, localvars)
    if _state.varlike.search(cmd):
        _state.output.write(
            f"Warning: There is a potential un-substituted variable in the command\n     {cmd}\n",
        )
    e = None
    try:
        # Force dispatch by temporarily ensuring the if_stack is all-true.
        # Some metacommand handlers check if_stack internally (e.g., the
        # dispatch table's eval() method checks run_when_false).  Since
        # the AST executor already handles branching, we need dispatch to
        # always run the handler.
        applies, result = _state.metacommandlist.eval(cmd)
        if applies:
            return result
    except ErrInfo as errinfo:
        e = errinfo
    except SystemExit:
        raise
    except Exception:
        e = ErrInfo(type="exception", exception_msg=exception_desc())
    if e:
        from execsql.utils.errors import stamp_errinfo

        stamp_errinfo(e)
        _state.status.metacommand_error = True
        _state.subvars.add_substitution("$LAST_ERROR", cmd)
        _state.subvars.add_substitution("$ERROR_MESSAGE", e.errmsg())
        if _state.exec_log is not None:
            _state.exec_log.log_status_info(f"Metacommand error: {e.errmsg()}")
        if _state.status.halt_on_metacommand_err:
            raise e
    # Unknown metacommand
    _state.status.metacommand_error = True
    raise ErrInfo(type="cmd", command_text=cmd, other_msg="Unknown metacommand")


# ---------------------------------------------------------------------------
# Core tree walker
# ---------------------------------------------------------------------------


def _execute_nodes(
    nodes: list[Node],
    source: str,
    localvars: SubVarSet | None = None,
    *,
    in_loop: bool = False,
) -> None:
    """Execute a list of AST nodes sequentially.

    Args:
        nodes: The nodes to execute.
        source: Source file name (for system variable updates).
        localvars: Local/parameter variable overlay for SCRIPT blocks.
        in_loop: True if we're inside a LOOP body — enables deferred
            variable conversion.
    """
    from execsql.script.engine import set_dynamic_system_vars

    for node in nodes:
        set_dynamic_system_vars()
        _set_command_vars(node.span.file, node.span.start_line)

        # Debug step mode
        if _state.step_mode:
            _state.step_mode = False
            from execsql.debug.repl import _debug_repl

            _debug_repl(step=True)

        # Profiling
        profiling = _state.profile_data is not None
        if profiling:
            t0 = _time.perf_counter()

        _execute_node(node, localvars, in_loop=in_loop)

        if profiling:
            elapsed = _time.perf_counter() - t0
            cmd_type = _node_cmd_type(node)
            cmd_text = _node_cmd_text(node)[:100]
            _state.profile_data.append(
                (node.span.file, node.span.start_line, cmd_type, elapsed, cmd_text),
            )

        _state.cmds_run += 1


def _execute_node(
    node: Node,
    localvars: SubVarSet | None = None,
    *,
    in_loop: bool = False,
) -> None:
    """Execute a single AST node."""
    if isinstance(node, SqlStatement):
        text = node.text
        if in_loop:
            text = _convert_deferred_vars(text)
        # Deduplicate trailing semicolons (matches SqlStmt.__init__)
        text = re.sub(r"\s*;(\s*;\s*)+$", ";", text)
        if node.span.file != "<inline>":
            _state.last_command = _FakeScriptCmd(node)
        _exec_sql(
            text,
            node.span.file,
            node.span.start_line,
            localvars,
            commit=not _state.status.batch.in_batch(),
        )

    elif isinstance(node, MetaCommandStatement):
        command = node.command
        if in_loop:
            command = _convert_deferred_vars(command)
        # Intercept BREAK before dispatch — it controls loop flow
        expanded = substitute_vars(command, localvars)
        if _BREAK_RX.match(expanded):
            raise _BreakLoop
        _state.last_command = _FakeScriptCmd(node)
        _exec_metacommand(command, node.span.file, node.span.start_line, localvars)

    elif isinstance(node, IfBlock):
        _execute_if(node, localvars, in_loop=in_loop)

    elif isinstance(node, LoopBlock):
        _execute_loop(node, localvars)

    elif isinstance(node, BatchBlock):
        _execute_batch(node, localvars, in_loop=in_loop)

    elif isinstance(node, ScriptBlock):
        _register_script_block(node)

    elif isinstance(node, SqlBlock):
        _execute_sql_block(node, localvars, in_loop=in_loop)

    elif isinstance(node, IncludeDirective):
        _execute_include(node, localvars)


# ---------------------------------------------------------------------------
# Block executors
# ---------------------------------------------------------------------------


def _execute_if(
    node: IfBlock,
    localvars: SubVarSet | None = None,
    *,
    in_loop: bool = False,
) -> None:
    """Evaluate an IF block and execute the matching branch."""
    if _eval_condition(node.condition, node.condition_modifiers):
        _execute_nodes(node.body, node.span.file, localvars, in_loop=in_loop)
        return

    # Try ELSEIF clauses
    for clause in node.elseif_clauses:
        expanded = substitute_vars(clause.condition)
        if _state.xcmd_test(expanded):
            _execute_nodes(clause.body, node.span.file, localvars, in_loop=in_loop)
            return

    # ELSE branch
    if node.else_body:
        _execute_nodes(node.else_body, node.span.file, localvars, in_loop=in_loop)


def _execute_loop(
    node: LoopBlock,
    localvars: SubVarSet | None = None,
) -> None:
    """Execute a LOOP WHILE or LOOP UNTIL block."""
    # Convert deferred vars in the condition — they re-evaluate each iteration
    condition = _convert_deferred_vars(node.condition)

    if node.loop_type == "WHILE":
        while True:
            expanded = substitute_vars(condition)
            if not _state.xcmd_test(expanded):
                break
            try:
                _execute_nodes(node.body, node.span.file, localvars, in_loop=True)
            except _BreakLoop:
                break
    else:  # UNTIL
        while True:
            try:
                _execute_nodes(node.body, node.span.file, localvars, in_loop=True)
            except _BreakLoop:
                break
            expanded = substitute_vars(condition)
            if _state.xcmd_test(expanded):
                break


def _execute_batch(
    node: BatchBlock,
    localvars: SubVarSet | None = None,
    *,
    in_loop: bool = False,
) -> None:
    """Execute a BEGIN BATCH / END BATCH block."""
    _state.status.batch.new_batch()
    try:
        _execute_nodes(node.body, node.span.file, localvars, in_loop=in_loop)
    finally:
        # END BATCH commits; if an error occurred, the batch handler
        # manages rollback via the existing BatchLevels logic.
        if _state.status.batch.in_batch():
            _state.status.batch.end_batch()


def _register_script_block(node: ScriptBlock) -> None:
    """Register a named SCRIPT block in _state.savedscripts.

    The block is stored as a CommandList for compatibility with the
    existing EXECUTE SCRIPT dispatch handler.
    """
    from execsql.script.engine import CommandList

    # Convert AST nodes back to ScriptCmd objects for compatibility
    # with the existing ScriptExecSpec.execute() handler.
    cmdlist = _flatten_for_legacy(node.body, node.span.file)
    cl = CommandList(cmdlist, node.name, node.param_names)
    _state.savedscripts[node.name] = cl


def _flatten_for_legacy(nodes: list[Node], source: str) -> list:
    """Convert AST nodes to flat ScriptCmd list for legacy compatibility."""
    from execsql.script.engine import MetacommandStmt, ScriptCmd, SqlStmt

    result = []
    for node in nodes:
        if isinstance(node, SqlStatement):
            text = re.sub(r"\s*;(\s*;\s*)+$", ";", node.text)
            result.append(
                ScriptCmd(node.span.file, node.span.start_line, "sql", SqlStmt(text)),
            )
        elif isinstance(node, MetaCommandStatement):
            result.append(
                ScriptCmd(node.span.file, node.span.start_line, "cmd", MetacommandStmt(node.command)),
            )
        elif isinstance(node, IfBlock):
            # Flatten IF/ELSE/ENDIF back to flat metacommands for legacy
            result.append(
                ScriptCmd(
                    node.span.file,
                    node.span.start_line,
                    "cmd",
                    MetacommandStmt(f"IF ({node.condition})"),
                ),
            )
            result.extend(_flatten_for_legacy(node.body, source))
            for clause in node.elseif_clauses:
                result.append(
                    ScriptCmd(
                        clause.span.file,
                        clause.span.start_line,
                        "cmd",
                        MetacommandStmt(f"ELSEIF ({clause.condition})"),
                    ),
                )
                result.extend(_flatten_for_legacy(clause.body, source))
            if node.else_body:
                result.append(
                    ScriptCmd(
                        node.span.file,
                        node.else_span.start_line if node.else_span else node.span.start_line,
                        "cmd",
                        MetacommandStmt("ELSE"),
                    ),
                )
                result.extend(_flatten_for_legacy(node.else_body, source))
            result.append(
                ScriptCmd(
                    node.span.file,
                    node.span.effective_end_line,
                    "cmd",
                    MetacommandStmt("ENDIF"),
                ),
            )
        elif isinstance(node, LoopBlock):
            result.append(
                ScriptCmd(
                    node.span.file,
                    node.span.start_line,
                    "cmd",
                    MetacommandStmt(f"LOOP {node.loop_type} ({node.condition})"),
                ),
            )
            result.extend(_flatten_for_legacy(node.body, source))
            result.append(
                ScriptCmd(
                    node.span.file,
                    node.span.effective_end_line,
                    "cmd",
                    MetacommandStmt("END LOOP"),
                ),
            )
        elif isinstance(node, BatchBlock):
            result.append(
                ScriptCmd(node.span.file, node.span.start_line, "cmd", MetacommandStmt("BEGIN BATCH")),
            )
            result.extend(_flatten_for_legacy(node.body, source))
            result.append(
                ScriptCmd(node.span.file, node.span.effective_end_line, "cmd", MetacommandStmt("END BATCH")),
            )
        elif isinstance(node, SqlBlock):
            # Flatten SQL block contents
            result.extend(_flatten_for_legacy(node.body, source))
        elif isinstance(node, IncludeDirective):
            if node.is_execute_script:
                parts = ["EXECUTE SCRIPT"]
                if node.if_exists:
                    parts.append("IF EXISTS")
                parts.append(node.target)
                if node.arguments:
                    parts.append(f"WITH ARGS ({node.arguments})")
                if node.loop_type:
                    parts.append(f"{node.loop_type} ({node.loop_condition})")
                result.append(
                    ScriptCmd(node.span.file, node.span.start_line, "cmd", MetacommandStmt(" ".join(parts))),
                )
            else:
                prefix = "INCLUDE IF EXISTS" if node.if_exists else "INCLUDE"
                result.append(
                    ScriptCmd(node.span.file, node.span.start_line, "cmd", MetacommandStmt(f"{prefix} {node.target}")),
                )
    return result


def _execute_sql_block(
    node: SqlBlock,
    localvars: SubVarSet | None = None,
    *,
    in_loop: bool = False,
) -> None:
    """Execute a BEGIN SQL / END SQL block."""
    # SQL blocks contain one or more SqlStatements; execute them normally.
    _execute_nodes(node.body, node.span.file, localvars, in_loop=in_loop)


def _execute_include(
    node: IncludeDirective,
    localvars: SubVarSet | None = None,
) -> None:
    """Execute an INCLUDE or EXECUTE SCRIPT directive.

    Both INCLUDE and EXECUTE SCRIPT are dispatched through the metacommand
    table, which pushes new CommandList objects onto ``_state.commandliststack``.
    After dispatch, we drain the stack by calling ``runscripts()``, which
    executes the pushed commands using the legacy engine.

    This hybrid approach is necessary because INCLUDE resolution involves
    complex file path logic and EXECUTE SCRIPT handles argument parsing,
    parameter binding, and loop wrapping — all implemented in the dispatch
    handlers.
    """
    from execsql.script.engine import runscripts

    if node.is_execute_script:
        parts = ["EXECUTE SCRIPT"]
        if node.if_exists:
            parts.append("IF EXISTS")
        parts.append(node.target)
        if node.arguments:
            parts.append(f"WITH ARGS ({node.arguments})")
        if node.loop_type:
            parts.append(f"{node.loop_type} ({node.loop_condition})")
        cmd = " ".join(parts)
        _state.last_command = _FakeScriptCmd(node)
        _exec_metacommand(cmd, node.span.file, node.span.start_line, localvars)
    else:
        prefix = "INCLUDE IF EXISTS" if node.if_exists else "INCLUDE"
        cmd = f"{prefix} {node.target}"
        _state.last_command = _FakeScriptCmd(node)
        _exec_metacommand(cmd, node.span.file, node.span.start_line, localvars)

    # The dispatch handler may have pushed commands onto the stack.
    # Drain them using the legacy engine.
    if _state.commandliststack:
        runscripts()


# ---------------------------------------------------------------------------
# BREAK support
# ---------------------------------------------------------------------------


class _BreakLoop(Exception):
    """Raised by BREAK metacommand to exit the innermost loop."""


_BREAK_RX = re.compile(r"^\s*BREAK\s*$", re.I)


# ---------------------------------------------------------------------------
# Fake ScriptCmd for _state.last_command compatibility
# ---------------------------------------------------------------------------


class _FakeScriptCmd:
    """Minimal stand-in for ScriptCmd to satisfy _state.last_command readers."""

    __slots__ = ("source", "line_no", "source_dir", "source_name", "command", "command_type")

    def __init__(self, node: Node) -> None:
        self.source = node.span.file
        self.line_no = node.span.start_line
        _p = Path(node.span.file)
        self.source_dir = str(_p.resolve().parent) + os.sep
        self.source_name = _p.name
        self.command_type = "sql" if isinstance(node, SqlStatement) else "cmd"
        if isinstance(node, SqlStatement):
            self.command = type("_cmd", (), {"statement": node.text, "commandline": lambda self: self.statement})()
        elif isinstance(node, MetaCommandStatement):
            self.command = type(
                "_cmd",
                (),
                {"statement": node.command, "commandline": lambda self: "-- !x! " + self.statement},
            )()
        else:
            self.command = type("_cmd", (), {"statement": "", "commandline": lambda self: ""})()

    def current_script_line(self) -> tuple:
        return (self.source, self.line_no)

    def commandline(self) -> str:
        return self.command.commandline()


# ---------------------------------------------------------------------------
# Node type/text helpers for profiling
# ---------------------------------------------------------------------------


def _node_cmd_type(node: Node) -> str:
    if isinstance(node, SqlStatement):
        return "sql"
    return "cmd"


def _node_cmd_text(node: Node) -> str:
    if isinstance(node, SqlStatement):
        return node.text
    if isinstance(node, MetaCommandStatement):
        return "-- !x! " + node.command
    if isinstance(node, IfBlock):
        return f"-- !x! IF ({node.condition})"
    if isinstance(node, LoopBlock):
        return f"-- !x! LOOP {node.loop_type} ({node.condition})"
    if isinstance(node, BatchBlock):
        return "-- !x! BEGIN BATCH"
    if isinstance(node, ScriptBlock):
        return f"-- !x! BEGIN SCRIPT {node.name}"
    if isinstance(node, IncludeDirective):
        if node.is_execute_script:
            return f"-- !x! EXECUTE SCRIPT {node.target}"
        return f"-- !x! INCLUDE {node.target}"
    return repr(node)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def execute(script: Script) -> None:
    """Execute an AST-parsed script.

    Requires that ``_state`` has been fully initialised (database connected,
    config loaded, metacommand dispatch table built, etc.).  This is
    typically done by ``_run()`` in ``execsql.cli.run``.

    Args:
        script: The parsed :class:`Script` tree to execute.
    """
    from execsql.script.engine import set_static_system_vars

    set_static_system_vars()
    _execute_nodes(script.body, script.source)
