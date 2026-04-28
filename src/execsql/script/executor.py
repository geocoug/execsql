"""AST-based script executor for execsql.

Walks a :class:`~execsql.script.ast.Script` tree and executes each node,
replacing the flat ``CommandList.run_next()`` loop for scripts parsed via
the AST parser.

Design:
    - **The executor owns control flow.**  IF conditions, LOOP iteration,
      and BATCH boundaries are driven by the tree structure — no
      ``if_stack`` or ``compiling_loop`` needed.
    - **SQL and metacommands delegate to the existing runtime.**  SQL is
      executed via the current database connection; metacommands are
      dispatched through ``ctx.metacommandlist.eval()``.  All 200+
      metacommand handlers work unchanged.
    - **Variable substitution** uses the existing ``substitute_vars()``.
    - **RuntimeContext is passed explicitly** as ``ctx`` — the first
      module migrated to instance-based context (Phase 2).  The public
      ``execute()`` function defaults to ``get_context()`` if no ``ctx``
      is provided, so callers that haven't migrated yet work unchanged.

Usage::

    from execsql.script.executor import execute
    from execsql.script.parser import parse_script

    tree = parse_script("pipeline.sql")
    execute(tree)  # uses global context

    # Or with an explicit context:
    from execsql.state import RuntimeContext, get_context
    ctx = get_context()
    execute(tree, ctx=ctx)
"""

from __future__ import annotations

import datetime
import os
import re
import time as _time
from pathlib import Path
from typing import Any

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
from execsql.script.engine import set_dynamic_system_vars, set_static_system_vars, substitute_vars
from execsql.script.variables import SubVarSet
from execsql.state import RuntimeContext, get_context, xcmd_test
from execsql.utils.errors import exception_desc

__all__ = ["execute"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Regex for deferred variable conversion: !{$VAR}! → !!$VAR!!
_DEFER_RX = re.compile(r"!\{([$@&~#+]?\w+)\}!")

# Compiled regex to match prefixed variables (for unsubstituted-var warnings)
_VARLIKE = re.compile(r"!![$@&~#]?\w+!!", re.I)

# Module-level registry of ScriptBlock AST nodes for native EXECUTE SCRIPT.
# Keyed by lowercased script name. Populated by _register_script_block(),
# consumed by _execute_include().
_ast_scripts: dict[str, ScriptBlock] = {}


def _convert_deferred_vars(text: str) -> str:
    """Convert deferred substitution variables to regular ones.

    In loop bodies, ``!{$VAR}!`` is converted to ``!!$VAR!!`` so that
    variables are re-evaluated on each iteration instead of being captured
    once at loop entry.
    """
    return _DEFER_RX.sub(r"!!\1!!", text)


def _eval_condition(
    ctx: RuntimeContext,
    condition: str,
    modifiers: list[ConditionModifier] | None = None,
) -> bool:
    """Evaluate a condition string with optional ANDIF/ORIF modifiers."""
    expanded = substitute_vars(condition, ctx=ctx)
    result = xcmd_test(expanded)

    if modifiers:
        for mod in modifiers:
            mod_expanded = substitute_vars(mod.condition, ctx=ctx)
            mod_result = xcmd_test(mod_expanded)
            if mod.kind == "AND":
                result = result and mod_result
            else:  # OR
                result = result or mod_result

    return result


def _set_command_vars(ctx: RuntimeContext, source: str, line_no: int) -> None:
    """Set per-command system variables (current script, line, time)."""
    now = datetime.datetime.now()
    ctx.subvars.add_substitution("$CURRENT_TIME", now.strftime("%Y-%m-%d %H:%M"))
    ctx.subvars.add_substitution("$CURRENT_DATE", now.strftime("%Y-%m-%d"))
    utcnow = datetime.datetime.now(tz=datetime.timezone.utc)
    ctx.subvars.add_substitution("$CURRENT_TIME_UTC", utcnow.strftime("%Y-%m-%d %H:%M"))
    _p = Path(source)
    ctx.subvars.add_substitution("$CURRENT_SCRIPT", source)
    ctx.subvars.add_substitution("$CURRENT_SCRIPT_PATH", str(_p.resolve().parent) + os.sep)
    ctx.subvars.add_substitution("$CURRENT_SCRIPT_NAME", _p.name)
    ctx.subvars.add_substitution("$CURRENT_SCRIPT_LINE", str(line_no))
    ctx.subvars.add_substitution("$SCRIPT_LINE", str(line_no))


# ---------------------------------------------------------------------------
# SQL execution (bypasses SqlStmt.run's if_stack check)
# ---------------------------------------------------------------------------


def _exec_sql(
    ctx: RuntimeContext,
    text: str,
    source: str,
    line_no: int,
    localvars: SubVarSet | None = None,
    commit: bool = True,
) -> None:
    """Execute a SQL statement against the current database."""
    ctx.status.sql_error = False
    if ctx.status.batch.in_batch():
        ctx.status.batch.using_db(ctx.dbs.current())
    cmd = substitute_vars(text, localvars, ctx=ctx)
    if _VARLIKE.search(cmd):
        ctx.output.write(
            f"Warning: There is a potential un-substituted variable in the command\n     {cmd}\n",
        )
    e = None
    try:
        db = ctx.dbs.current()
        if ctx.conf.log_sql and ctx.exec_log:
            ctx.exec_log.log_sql_query(cmd, db.name(), line_no)
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
        ctx.subvars.add_substitution("$LAST_ERROR", cmd)
        ctx.subvars.add_substitution("$ERROR_MESSAGE", e.errmsg())
        ctx.status.sql_error = True
        if ctx.exec_log is not None:
            ctx.exec_log.log_status_info(f"SQL error: {e.errmsg()}")
        if ctx.status.halt_on_err:
            from execsql.utils.errors import exit_now

            exit_now(1, e)
        return
    ctx.subvars.add_substitution("$LAST_SQL", cmd)


# ---------------------------------------------------------------------------
# Metacommand execution (bypasses MetacommandStmt.run's if_stack check)
# ---------------------------------------------------------------------------


def _exec_metacommand(
    ctx: RuntimeContext,
    command: str,
    source: str,
    line_no: int,
    localvars: SubVarSet | None = None,
) -> Any:
    """Dispatch a metacommand through the dispatch table."""
    cmd = substitute_vars(command, localvars, ctx=ctx)
    if _VARLIKE.search(cmd):
        ctx.output.write(
            f"Warning: There is a potential un-substituted variable in the command\n     {cmd}\n",
        )
    e = None
    try:
        applies, result = ctx.metacommandlist.eval(cmd)
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
        ctx.status.metacommand_error = True
        ctx.subvars.add_substitution("$LAST_ERROR", cmd)
        ctx.subvars.add_substitution("$ERROR_MESSAGE", e.errmsg())
        if ctx.exec_log is not None:
            ctx.exec_log.log_status_info(f"Metacommand error: {e.errmsg()}")
        if ctx.status.halt_on_metacommand_err:
            raise e
    # Unknown metacommand
    ctx.status.metacommand_error = True
    raise ErrInfo(type="cmd", command_text=cmd, other_msg="Unknown metacommand")


# ---------------------------------------------------------------------------
# Core tree walker
# ---------------------------------------------------------------------------


def _execute_nodes(
    ctx: RuntimeContext,
    nodes: list[Node],
    source: str,
    localvars: SubVarSet | None = None,
    *,
    in_loop: bool = False,
) -> None:
    """Execute a list of AST nodes sequentially."""
    for node in nodes:
        set_dynamic_system_vars(ctx)
        _set_command_vars(ctx, node.span.file, node.span.start_line)

        # Debug step mode
        if ctx.step_mode:
            ctx.step_mode = False
            from execsql.debug.repl import _debug_repl

            _debug_repl(step=True)

        # Profiling
        profiling = ctx.profile_data is not None
        if profiling:
            t0 = _time.perf_counter()

        _execute_node(ctx, node, localvars, in_loop=in_loop)

        if profiling:
            elapsed = _time.perf_counter() - t0
            cmd_type = _node_cmd_type(node)
            cmd_text = _node_cmd_text(node)[:100]
            ctx.profile_data.append(
                (node.span.file, node.span.start_line, cmd_type, elapsed, cmd_text),
            )

        ctx.cmds_run += 1


def _execute_node(
    ctx: RuntimeContext,
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
            ctx.last_command = _FakeScriptCmd(node)
        _exec_sql(
            ctx,
            text,
            node.span.file,
            node.span.start_line,
            localvars,
            commit=not ctx.status.batch.in_batch(),
        )

    elif isinstance(node, MetaCommandStatement):
        command = node.command
        if in_loop:
            command = _convert_deferred_vars(command)
        # Intercept BREAK before dispatch — it controls loop flow
        expanded = substitute_vars(command, localvars, ctx=ctx)
        if _BREAK_RX.match(expanded):
            raise _BreakLoop
        ctx.last_command = _FakeScriptCmd(node)
        _exec_metacommand(ctx, command, node.span.file, node.span.start_line, localvars)

    elif isinstance(node, IfBlock):
        _execute_if(ctx, node, localvars, in_loop=in_loop)

    elif isinstance(node, LoopBlock):
        _execute_loop(ctx, node, localvars)

    elif isinstance(node, BatchBlock):
        _execute_batch(ctx, node, localvars, in_loop=in_loop)

    elif isinstance(node, ScriptBlock):
        _register_script_block(ctx, node)

    elif isinstance(node, SqlBlock):
        _execute_sql_block(ctx, node, localvars, in_loop=in_loop)

    elif isinstance(node, IncludeDirective):
        _execute_include(ctx, node, localvars)


# ---------------------------------------------------------------------------
# Block executors
# ---------------------------------------------------------------------------


def _execute_if(
    ctx: RuntimeContext,
    node: IfBlock,
    localvars: SubVarSet | None = None,
    *,
    in_loop: bool = False,
) -> None:
    """Evaluate an IF block and execute the matching branch."""
    if _eval_condition(ctx, node.condition, node.condition_modifiers):
        _execute_nodes(ctx, node.body, node.span.file, localvars, in_loop=in_loop)
        return

    # Try ELSEIF clauses
    for clause in node.elseif_clauses:
        expanded = substitute_vars(clause.condition, ctx=ctx)
        if xcmd_test(expanded):
            _execute_nodes(ctx, clause.body, node.span.file, localvars, in_loop=in_loop)
            return

    # ELSE branch
    if node.else_body:
        _execute_nodes(ctx, node.else_body, node.span.file, localvars, in_loop=in_loop)


def _execute_loop(
    ctx: RuntimeContext,
    node: LoopBlock,
    localvars: SubVarSet | None = None,
) -> None:
    """Execute a LOOP WHILE or LOOP UNTIL block."""
    # Convert deferred vars in the condition — they re-evaluate each iteration
    condition = _convert_deferred_vars(node.condition)

    if node.loop_type == "WHILE":
        while True:
            expanded = substitute_vars(condition, ctx=ctx)
            if not xcmd_test(expanded):
                break
            try:
                _execute_nodes(ctx, node.body, node.span.file, localvars, in_loop=True)
            except _BreakLoop:
                break
    else:  # UNTIL
        while True:
            try:
                _execute_nodes(ctx, node.body, node.span.file, localvars, in_loop=True)
            except _BreakLoop:
                break
            expanded = substitute_vars(condition, ctx=ctx)
            if xcmd_test(expanded):
                break


def _execute_batch(
    ctx: RuntimeContext,
    node: BatchBlock,
    localvars: SubVarSet | None = None,
    *,
    in_loop: bool = False,
) -> None:
    """Execute a BEGIN BATCH / END BATCH block."""
    ctx.status.batch.new_batch()
    try:
        _execute_nodes(ctx, node.body, node.span.file, localvars, in_loop=in_loop)
    finally:
        if ctx.status.batch.in_batch():
            ctx.status.batch.end_batch()


def _register_script_block(ctx: RuntimeContext, node: ScriptBlock) -> None:
    """Register a named SCRIPT block.

    Stores the AST node in ``_ast_scripts`` for native execution, and also
    builds a legacy ``CommandList`` in ``ctx.savedscripts`` so that dispatch
    table handlers (e.g., ON ERROR_HALT EXECUTE SCRIPT) still work.
    """
    from execsql.script.engine import CommandList

    # AST-native registry
    _ast_scripts[node.name] = node

    # Legacy compatibility — flatten to CommandList for dispatch table
    cmdlist = _flatten_for_legacy(node.body, node.span.file)
    cl = CommandList(cmdlist, node.name, node.param_names)
    ctx.savedscripts[node.name] = cl


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
    ctx: RuntimeContext,
    node: SqlBlock,
    localvars: SubVarSet | None = None,
    *,
    in_loop: bool = False,
) -> None:
    """Execute a BEGIN SQL / END SQL block."""
    _execute_nodes(ctx, node.body, node.span.file, localvars, in_loop=in_loop)


def _execute_include(
    ctx: RuntimeContext,
    node: IncludeDirective,
    localvars: SubVarSet | None = None,
) -> None:
    """Execute an INCLUDE or EXECUTE SCRIPT directive.

    EXECUTE SCRIPT is handled natively when the target is in ``_ast_scripts``:
    arguments are parsed, a local variable overlay is created, and the body
    is executed through the AST executor.  WHILE/UNTIL loops are handled
    natively too.

    INCLUDE and unresolved EXECUTE SCRIPT targets fall back to the dispatch
    table + legacy engine.
    """
    if node.is_execute_script:
        target = node.target.lower()

        # Native path: target is in our AST registry
        if target in _ast_scripts:
            _execute_script_native(ctx, node, _ast_scripts[target], localvars)
            return

        # Target not in AST registry — might be defined in an INCLUDE'd file
        # that hasn't been loaded yet.  Fall through to dispatch table.
        if not node.if_exists and target not in ctx.savedscripts:
            raise ErrInfo(
                "cmd",
                other_msg=f"There is no SCRIPT named {node.target}.",
            )
        if node.if_exists and target not in ctx.savedscripts:
            return  # IF EXISTS — skip silently

    # Fallback: dispatch through metacommand table (INCLUDE, or EXECUTE
    # SCRIPT for targets not in AST registry)
    _execute_include_legacy(ctx, node, localvars)


def _execute_script_native(
    ctx: RuntimeContext,
    node: IncludeDirective,
    script_block: ScriptBlock,
    localvars: SubVarSet | None = None,
) -> None:
    """Execute a SCRIPT block natively through the AST executor."""
    import copy

    from execsql.script.variables import ScriptArgSubVarSet
    from execsql.utils.strings import wo_quotes

    # Parse arguments (replicates ScriptExecSpec logic)
    script_localvars = None
    if node.arguments is not None:
        args_rx = re.compile(
            r'(?P<param>#?\w+)\s*=\s*(?P<arg>(?:(?:[^"\'\[][^,\)]*)|(?:"[^"]*")|(?:\'[^\']*\')|(?:\[[^\]]*\])))',
            re.I,
        )
        all_args = re.findall(args_rx, node.arguments)
        all_cleaned_args = [(ae[0], wo_quotes(ae[1])) for ae in all_args]
        all_prepared_args = [(ae[0] if ae[0][0] == "#" else "#" + ae[0], ae[1]) for ae in all_cleaned_args]
        scriptvarset = ScriptArgSubVarSet()
        for param, arg in all_prepared_args:
            scriptvarset.add_substitution(param, arg)

        # Validate parameter names match
        if script_block.param_names is not None:
            passed_names = [p[0].lstrip("#") for p in all_prepared_args]
            if not all(p in passed_names for p in script_block.param_names):
                raise ErrInfo(
                    "error",
                    other_msg=f"Formal and actual parameter name mismatch in call to {script_block.name}.",
                )
        script_localvars = scriptvarset
    else:
        if script_block.param_names is not None:
            raise ErrInfo(
                "error",
                other_msg=(
                    f"Missing expected parameters ({', '.join(script_block.param_names)}) "
                    f"in call to {script_block.name}."
                ),
            )

    # Merge script-local vars with any existing local vars
    merged = script_localvars

    def _run_body() -> None:
        # Deep-copy the body to avoid mutation across iterations
        body = copy.deepcopy(script_block.body)
        _execute_nodes(ctx, body, script_block.span.file, merged, in_loop=False)

    # Handle WHILE/UNTIL loops
    if node.loop_type == "WHILE":
        while True:
            condition = _convert_deferred_vars(node.loop_condition)
            expanded = substitute_vars(condition, ctx=ctx)
            if not xcmd_test(expanded):
                break
            try:
                _run_body()
            except _BreakLoop:
                break
    elif node.loop_type == "UNTIL":
        while True:
            try:
                _run_body()
            except _BreakLoop:
                break
            condition = _convert_deferred_vars(node.loop_condition)
            expanded = substitute_vars(condition, ctx=ctx)
            if xcmd_test(expanded):
                break
    else:
        _run_body()


def _execute_include_legacy(
    ctx: RuntimeContext,
    node: IncludeDirective,
    localvars: SubVarSet | None = None,
) -> None:
    """Fallback: dispatch INCLUDE or EXECUTE SCRIPT through the metacommand table."""
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
    else:
        prefix = "INCLUDE IF EXISTS" if node.if_exists else "INCLUDE"
        cmd = f"{prefix} {node.target}"

    ctx.last_command = _FakeScriptCmd(node)
    _exec_metacommand(ctx, cmd, node.span.file, node.span.start_line, localvars)

    # The dispatch handler may have pushed commands onto the stack.
    if ctx.commandliststack:
        runscripts()


# ---------------------------------------------------------------------------
# BREAK support
# ---------------------------------------------------------------------------


class _BreakLoop(Exception):
    """Raised by BREAK metacommand to exit the innermost loop."""


_BREAK_RX = re.compile(r"^\s*BREAK\s*$", re.I)


# ---------------------------------------------------------------------------
# Fake ScriptCmd for ctx.last_command compatibility
# ---------------------------------------------------------------------------


class _FakeScriptCmd:
    """Minimal stand-in for ScriptCmd to satisfy ctx.last_command readers."""

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


def execute(script: Script, *, ctx: RuntimeContext | None = None) -> None:
    """Execute an AST-parsed script.

    Args:
        script: The parsed :class:`Script` tree to execute.
        ctx: The :class:`RuntimeContext` to use.  Defaults to the global
            context via :func:`get_context` if not provided.
    """
    if ctx is None:
        ctx = get_context()

    _ast_scripts.clear()
    set_static_system_vars(ctx)
    _execute_nodes(ctx, script.body, script.source)
