"""AST-based script executor for execsql.

Walks a :class:`~execsql.script.ast.Script` tree and executes each node.
This is the only execution engine; the parser produces the tree, this
module runs it.

Design:
    - **Control flow is tree-driven.** IF conditions, LOOP iteration, and
      BATCH boundaries are resolved by walking nested nodes, not by
      runtime state flags.
    - **SQL and metacommands delegate to the existing runtime.** SQL
      runs against the active database connection; metacommands are
      dispatched through ``ctx.metacommandlist.eval()`` (the same
      ~225-entry dispatch table the rest of the codebase uses).
    - **Variable substitution** uses :func:`execsql.script.engine.substitute_vars`.
    - **Context is explicit.** :func:`execute` takes a
      :class:`~execsql.state.RuntimeContext` via the ``ctx`` keyword;
      when omitted it falls back to :func:`~execsql.state.get_context`.
      For tracking and error reporting the executor pushes
      :class:`~execsql.state.ExecFrame` records onto
      ``ctx.ast_exec_stack`` as it descends into IF / LOOP / BATCH /
      INCLUDE'd files / ``EXECUTE SCRIPT`` calls. Scope frames
      (``main``, ``script``) carry the active ``localvars`` and
      ``paramvals``; block frames cache a ``scope_ref`` to the
      enclosing scope for O(1) variable lookup.

Usage::

    from execsql.script.executor import execute
    from execsql.script.parser import parse_script

    tree = parse_script("pipeline.sql")
    execute(tree)  # uses the thread-local context

    # Or with an explicit context:
    from execsql.state import RuntimeContext, active_context
    ctx = RuntimeContext()
    with active_context(ctx):
        execute(tree, ctx=ctx)
"""

from __future__ import annotations

import copy
import datetime
import os
import re
import time as _time
from pathlib import Path
from typing import Any, cast

from execsql.exceptions import ErrInfo
from execsql.script.ast import (
    BatchBlock,
    Comment,
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
from execsql.state import ExecFrame, RuntimeContext, active_context, get_context, xcmd_test
from execsql.utils.errors import exception_desc, exit_now, stamp_errinfo

__all__ = ["execute"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Regex for deferred variable conversion: !{$VAR}! → !!$VAR!!
_DEFER_RX = re.compile(r"!\{([$@&~#+]?\w+)\}!")

# Compiled regex to match prefixed variables (for unsubstituted-var warnings)
_VARLIKE = re.compile(r"!![$@&~#]?\w+!!", re.I)


def _stack_localvars(ctx: RuntimeContext) -> SubVarSet | None:
    """Build the merged ``~`` local + ``#`` param overlay for the current scope.

    Returns ``localvars.merge(paramvals)`` for the innermost SCRIPT or
    ``<main>`` scope frame, or ``None`` if the exec stack is empty.  This is
    the canonical "current variable scope" used by ``substitute_vars`` and
    ``get_subvarset`` so that ``x_sub``, ``x_rm_sub``, condition predicates,
    and prompt handlers all see the same overlay.
    """
    scope = ctx.current_scope()
    if scope is None:
        return None
    localvars = scope.localvars
    if localvars is None:
        return None
    return cast(SubVarSet, localvars.merge(scope.paramvals))


def _assert_command_runtime(ctx: RuntimeContext) -> None:
    """Assert runtime singletons required by command execution are initialised."""
    assert ctx.conf is not None
    assert ctx.dbs is not None
    assert ctx.metacommandlist is not None
    assert ctx.output is not None
    assert ctx.status is not None
    assert ctx.subvars is not None


def _push_frame(
    ctx: RuntimeContext,
    name: str,
    source: str,
    line_no: int = 0,
    *,
    paramnames: list[str] | None = None,
    kind: str = "script",
) -> ExecFrame:
    """Push a scope frame onto the unified AST execution stack.

    Creates an :class:`ExecFrame` of ``kind`` ``"main"`` or ``"script"`` with a
    fresh :class:`LocalSubVarSet` and the declared ``paramnames``.  Returns
    the frame so the caller can set ``paramvals`` after parsing the call's
    arguments.
    """
    from execsql.script.variables import LocalSubVarSet

    frame = ExecFrame(
        kind=kind,
        label=name,
        source=source,
        line=line_no or None,
        localvars=LocalSubVarSet(),
        paramnames=paramnames,
    )
    ctx.ast_exec_stack.append(frame)
    return frame


def _pop_frame(ctx: RuntimeContext) -> None:
    """Pop the top scope frame from the AST execution stack."""
    if ctx.ast_exec_stack:
        ctx.ast_exec_stack.pop()


def _push_block_frame(ctx: RuntimeContext, frame: ExecFrame) -> None:
    """Push a non-scope frame (if/loop/batch/include) onto the exec stack.

    Caches a reference to the enclosing SCRIPT/main scope on the frame so
    that ``current_localvars()`` stays O(1) regardless of nesting depth.
    """
    frame.scope_ref = ctx.current_scope()
    ctx.ast_exec_stack.append(frame)


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
    """Evaluate a condition string with optional ANDIF/ORIF modifiers.

    Short-circuits ANDIF (stops on first False) and ORIF (stops on first True)
    so that patterns like ``IF (sub_defined(x)) ANDIF (not sub_empty(x))``
    don't evaluate ``sub_empty`` when ``x`` is undefined.
    """
    effective_locals = _stack_localvars(ctx)
    expanded = substitute_vars(condition, effective_locals, ctx=ctx)
    result = xcmd_test(expanded)

    if modifiers:
        for mod in modifiers:
            # Short-circuit: AND with False can't become True,
            # OR with True can't become False.
            if mod.kind == "AND" and not result:
                continue
            if mod.kind == "OR" and result:
                continue
            mod_expanded = substitute_vars(mod.condition, effective_locals, ctx=ctx)
            mod_result = xcmd_test(mod_expanded)
            if mod.kind == "AND":
                result = result and mod_result
            else:  # OR
                result = result or mod_result

    return result


def _set_command_vars(ctx: RuntimeContext, source: str, line_no: int) -> None:
    """Set per-command system variables (current script, line, time)."""
    assert ctx.subvars is not None
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
# SQL execution
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
    _assert_command_runtime(ctx)
    conf = ctx.conf
    dbs = ctx.dbs
    output = ctx.output
    status = ctx.status
    subvars = ctx.subvars
    assert conf is not None
    assert dbs is not None
    assert output is not None
    assert status is not None
    assert subvars is not None

    status.sql_error = False
    if status.batch.in_batch():
        status.batch.using_db(dbs.current())
    # Build localvars from the command-list stack frame so that ~ and # vars
    # written by x_sub/get_subvarset are visible.  The stack frame is the
    # canonical source; the `localvars` parameter is kept for backward compat
    # but superseded when the stack is populated.
    effective_locals = _stack_localvars(ctx) or localvars
    cmd = substitute_vars(text, effective_locals, ctx=ctx)
    if _VARLIKE.search(cmd):
        output.write(
            f"Warning: There is a potential un-substituted variable in the command\n     {cmd}\n",
        )
    e = None
    try:
        db = dbs.current()
        if conf.log_sql and ctx.exec_log:
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
        stamp_errinfo(e)
        subvars.add_substitution("$LAST_ERROR", cmd)
        subvars.add_substitution("$ERROR_MESSAGE", e.errmsg())
        status.sql_error = True
        if ctx.exec_log is not None:
            ctx.exec_log.log_status_info(f"SQL error: {e.errmsg()}")
        if status.halt_on_err:
            exit_now(1, e)
        status.error_history.append((source, line_no, cmd, e.errmsg()))
        return
    subvars.add_substitution("$LAST_SQL", cmd)


# ---------------------------------------------------------------------------
# Metacommand execution
# ---------------------------------------------------------------------------


def _exec_metacommand(
    ctx: RuntimeContext,
    cmd: str,
    source: str,
    line_no: int,
) -> Any:
    """Dispatch a metacommand through the dispatch table.

    *cmd* must already have ``!!$VAR!!`` substitution applied.  The caller is
    responsible for expansion so that side-effecting substitutions (counter
    increments, ``$RANDOM``, ``$UUID``) are evaluated exactly once per
    metacommand reference.
    """
    _assert_command_runtime(ctx)
    metacommandlist = ctx.metacommandlist
    output = ctx.output
    status = ctx.status
    subvars = ctx.subvars
    assert metacommandlist is not None
    assert output is not None
    assert status is not None
    assert subvars is not None

    if _VARLIKE.search(cmd):
        output.write(
            f"Warning: There is a potential un-substituted variable in the command\n     {cmd}\n",
        )
    e = None
    try:
        applies, result = metacommandlist.eval(cmd)
        if applies:
            return result
    except ErrInfo as errinfo:
        e = errinfo
    except SystemExit:
        raise
    except Exception:
        e = ErrInfo(type="exception", exception_msg=exception_desc())
    if e:
        stamp_errinfo(e)
        status.metacommand_error = True
        subvars.add_substitution("$LAST_ERROR", cmd)
        subvars.add_substitution("$ERROR_MESSAGE", e.errmsg())
        if ctx.exec_log is not None:
            ctx.exec_log.log_status_info(f"Metacommand error: {e.errmsg()}")
        if status.halt_on_metacommand_err:
            raise e
        status.error_history.append((source, line_no, cmd, e.errmsg()))
        return None
    # No handler matched — truly unknown metacommand
    status.metacommand_error = True
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
        if isinstance(node, Comment):
            continue  # Comments have no runtime semantics
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
            profile_data = ctx.profile_data
            assert profile_data is not None
            profile_data.append(
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
    assert ctx.status is not None
    if isinstance(node, SqlStatement):
        text = node.text
        if in_loop:
            text = _convert_deferred_vars(text)
        # Deduplicate trailing semicolons (matches SqlStmt.__init__)
        text = re.sub(r"\s*;(\s*;\s*)+$", ";", text)
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
        # Substitute once: the same expanded text is used for BREAK detection
        # and dispatch.  Calling substitute_vars twice would double-increment
        # !!$COUNTER_N!! and re-roll !!$RANDOM!!/!!$UUID!! references.
        effective_locals = _stack_localvars(ctx) or localvars
        expanded = substitute_vars(command, effective_locals, ctx=ctx)
        if _BREAK_RX.match(expanded):
            raise _BreakLoop
        ctx.last_command = _FakeScriptCmd(node)
        _exec_metacommand(ctx, expanded, node.span.file, node.span.start_line)

    elif isinstance(node, IfBlock):
        ctx.last_command = _FakeScriptCmd(node)
        _execute_if(ctx, node, localvars, in_loop=in_loop)

    elif isinstance(node, LoopBlock):
        ctx.last_command = _FakeScriptCmd(node)
        _execute_loop(ctx, node, localvars)

    elif isinstance(node, BatchBlock):
        ctx.last_command = _FakeScriptCmd(node)
        _execute_batch(ctx, node, localvars, in_loop=in_loop)

    elif isinstance(node, ScriptBlock):
        ctx.last_command = _FakeScriptCmd(node)
        _register_script_block(ctx, node)

    elif isinstance(node, SqlBlock):
        ctx.last_command = _FakeScriptCmd(node)
        _execute_sql_block(ctx, node, localvars, in_loop=in_loop)

    elif isinstance(node, IncludeDirective):
        ctx.last_command = _FakeScriptCmd(node)
        _execute_include(ctx, node, localvars)

    else:
        raise ErrInfo(
            type="error",
            other_msg=f"Unhandled AST node type: {type(node).__name__} at {node.span}",
        )


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
    """Evaluate an IF block and execute the matching branch.

    Pushes an :class:`ExecFrame` onto ``ctx.ast_exec_stack`` for the active
    branch while its body executes, so the debug REPL and
    ``DEBUG WRITE COMMANDLISTSTACK`` see the current IF nesting.
    """
    from execsql.state import ExecFrame

    if _eval_condition(ctx, node.condition, node.condition_modifiers):
        _push_block_frame(
            ctx,
            ExecFrame(kind="if", label=node.condition, source=node.span.file, line=node.span.start_line),
        )
        try:
            _execute_nodes(ctx, node.body, node.span.file, localvars, in_loop=in_loop)
        finally:
            ctx.ast_exec_stack.pop()
        return

    # Try ELSEIF clauses
    for clause in node.elseif_clauses:
        if _eval_condition(ctx, clause.condition, clause.condition_modifiers):
            _push_block_frame(
                ctx,
                ExecFrame(kind="elseif", label=clause.condition, source=node.span.file, line=node.span.start_line),
            )
            try:
                _execute_nodes(ctx, clause.body, node.span.file, localvars, in_loop=in_loop)
            finally:
                ctx.ast_exec_stack.pop()
            return

    # ELSE branch
    if node.else_body:
        _push_block_frame(
            ctx,
            ExecFrame(kind="else", label="", source=node.span.file, line=node.span.start_line),
        )
        try:
            _execute_nodes(ctx, node.else_body, node.span.file, localvars, in_loop=in_loop)
        finally:
            ctx.ast_exec_stack.pop()


def _execute_loop(
    ctx: RuntimeContext,
    node: LoopBlock,
    localvars: SubVarSet | None = None,
) -> None:
    """Execute a LOOP WHILE or LOOP UNTIL block."""
    from execsql.state import ExecFrame

    # Convert deferred vars in the condition — they re-evaluate each iteration
    condition = _convert_deferred_vars(node.condition)

    kind = "loop_while" if node.loop_type == "WHILE" else "loop_until"
    frame = ExecFrame(kind=kind, label=node.condition, source=node.span.file, line=node.span.start_line, iteration=0)
    _push_block_frame(ctx, frame)
    try:
        if node.loop_type == "WHILE":
            while True:
                effective_locals = _stack_localvars(ctx)
                expanded = substitute_vars(condition, effective_locals, ctx=ctx)
                if not xcmd_test(expanded):
                    break
                frame.iteration += 1
                try:
                    _execute_nodes(ctx, node.body, node.span.file, localvars, in_loop=True)
                except _BreakLoop:
                    break
        else:  # UNTIL
            while True:
                frame.iteration += 1
                try:
                    _execute_nodes(ctx, node.body, node.span.file, localvars, in_loop=True)
                except _BreakLoop:
                    break
                effective_locals = _stack_localvars(ctx)
                expanded = substitute_vars(condition, effective_locals, ctx=ctx)
                if xcmd_test(expanded):
                    break
    finally:
        ctx.ast_exec_stack.pop()


def _execute_batch(
    ctx: RuntimeContext,
    node: BatchBlock,
    localvars: SubVarSet | None = None,
    *,
    in_loop: bool = False,
) -> None:
    """Execute a BEGIN BATCH / END BATCH block."""
    from execsql.state import ExecFrame

    status = ctx.status
    assert status is not None
    status.batch.new_batch()
    _push_block_frame(
        ctx,
        ExecFrame(kind="batch", label="", source=node.span.file, line=node.span.start_line),
    )
    try:
        _execute_nodes(ctx, node.body, node.span.file, localvars, in_loop=in_loop)
    finally:
        ctx.ast_exec_stack.pop()
        if status.batch.in_batch():
            status.batch.end_batch()


def _pre_register_scripts(ctx: RuntimeContext, nodes: list[Node]) -> None:
    """Pre-scan AST nodes and register all ScriptBlock definitions.

    The legacy engine used a two-pass approach — parse first (registering all
    BEGIN SCRIPT blocks), then execute.  The AST executor walks the tree in a
    single pass, so forward references (EXECUTE SCRIPT before BEGIN SCRIPT)
    would fail.  This pre-scan restores compatibility by registering all script
    blocks before execution begins.

    Only scans the top level and inside IF/ELSE blocks — SCRIPT blocks inside
    LOOPs or other SCRIPTs are not pre-registered (matching legacy behavior
    where nested definitions weren't visible until the enclosing block ran).
    """
    for node in nodes:
        if isinstance(node, ScriptBlock):
            _register_script_block(ctx, node)
        elif isinstance(node, IfBlock):
            # Scripts defined inside IF branches should be registered too,
            # since the legacy parser registered them unconditionally at
            # parse time regardless of the IF condition.
            _pre_register_scripts(ctx, node.body)
            for clause in node.elseif_clauses:
                _pre_register_scripts(ctx, clause.body)
            if node.else_body:
                _pre_register_scripts(ctx, node.else_body)


def _register_script_block(ctx: RuntimeContext, node: ScriptBlock) -> None:
    """Register a named SCRIPT block in the AST script registry."""
    ctx.ast_scripts[node.name] = node


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

    **INCLUDE** is handled natively: the target file is parsed by the AST
    parser and executed through the AST executor with circular-include
    detection.

    **EXECUTE SCRIPT** is handled natively when the target is in
    ``ctx.ast_scripts``: arguments are parsed, a local variable overlay
    is created, and the body is executed through the AST executor.
    WHILE/UNTIL loops are handled natively too.
    """
    if node.is_execute_script:
        # Substitute variables in the target — the script name may be passed
        # as a parameter (e.g., EXECUTE SCRIPT !!#script_name!!).
        effective_locals = _stack_localvars(ctx) or localvars
        target = substitute_vars(node.target, effective_locals, ctx=ctx).strip().lower()

        # Native path: target is in our AST registry
        if target in ctx.ast_scripts:
            _execute_script_native(ctx, node, ctx.ast_scripts[target], localvars)
            return

        # Target not registered — IF EXISTS silently skips; otherwise error.
        if node.if_exists:
            return
        raise ErrInfo(
            "cmd",
            other_msg=f"There is no SCRIPT named {node.target}.",
        )

    # --- INCLUDE (file inclusion) — parse and execute natively ---
    _execute_include_native(ctx, node, localvars)


def _execute_script_native(
    ctx: RuntimeContext,
    node: IncludeDirective,
    script_block: ScriptBlock,
    localvars: SubVarSet | None = None,
) -> None:
    """Execute a SCRIPT block natively through the AST executor.

    Pushes a SCRIPT-kind :class:`~execsql.state.ExecFrame` onto
    ``ctx.ast_exec_stack`` so that metacommand handlers (``x_sub``,
    ``x_rm_sub``, ``xf_sub_defined``, prompt handlers, etc.) can access
    ``~`` local variables and ``#`` script arguments via
    ``ctx.current_localvars()`` / ``ctx.current_paramvals()``. The frame
    is popped on exit (including on error) via ``try/finally``.
    """
    from execsql.script.variables import ScriptArgSubVarSet
    from execsql.utils.strings import wo_quotes

    # Parse arguments (replicates ScriptExecSpec logic)
    # Expand the argument string in the *caller's* scope so that references
    # like val=!!#parent_param!! or val=!!~parent_local!! resolve correctly
    # before we push a new scope for this script.
    paramvals: ScriptArgSubVarSet | None = None
    if node.arguments is not None:
        caller_locals = _stack_localvars(ctx)
        expanded_args = substitute_vars(node.arguments, caller_locals, ctx=ctx)
        args_rx = re.compile(
            r'(?P<param>#?\w+)\s*=\s*(?P<arg>(?:(?:[^"\'\[][^,\)]*)|(?:"[^"]*")|(?:\'[^\']*\')|(?:\[[^\]]*\])))',
            re.I,
        )
        all_args = re.findall(args_rx, expanded_args)
        all_cleaned_args = [(ae[0], wo_quotes(ae[1])) for ae in all_args]
        all_prepared_args = [(ae[0] if ae[0][0] == "#" else "#" + ae[0], ae[1]) for ae in all_cleaned_args]
        paramvals = ScriptArgSubVarSet()
        for param, arg in all_prepared_args:
            paramvals.add_substitution(param, arg)

        # Validate parameter names match — with default parameter support
        if script_block.param_defs is not None:
            passed_names = [p[0].lstrip("#") for p in all_prepared_args]
            required = [p.name for p in script_block.param_defs if p.required]
            missing = [p for p in required if p not in passed_names]
            if missing:
                raise ErrInfo(
                    "error",
                    other_msg=(f"Missing required parameter(s) ({', '.join(missing)}) in call to {script_block.name}."),
                )
            # Inject defaults for optional params not provided
            for pdef in script_block.param_defs:
                if pdef.default is not None and pdef.name not in passed_names:
                    paramvals.add_substitution(f"#{pdef.name}", pdef.default)
    else:
        if script_block.param_defs is not None:
            required = [p.name for p in script_block.param_defs if p.required]
            if required:
                raise ErrInfo(
                    "error",
                    other_msg=(
                        f"Missing required parameter(s) ({', '.join(required)}) in call to {script_block.name}."
                    ),
                )
            # No args provided but all params have defaults — inject them all
            paramvals = ScriptArgSubVarSet()
            for pdef in script_block.param_defs:
                if pdef.default is not None:
                    paramvals.add_substitution(f"#{pdef.name}", pdef.default)

    # Push a SCRIPT-kind ExecFrame onto ast_exec_stack so that:
    #   - get_subvarset() can find ~local and +outer-scope variables
    #   - xf_sub_defined/xf_sub_empty can check ~local and #param variables
    #   - current_script_line() returns meaningful source location
    #   - REPL .vars/.stack commands show the correct scope
    frame = _push_frame(
        ctx,
        script_block.name,
        script_block.span.file,
        script_block.span.start_line,
        paramnames=script_block.param_names,
        kind="script",
    )
    if paramvals is not None:
        frame.paramvals = paramvals
        frame.params = dict(paramvals.substitutions)

    try:

        def _run_body() -> None:
            # Deep-copy the body to avoid mutation across iterations
            body = copy.deepcopy(script_block.body)
            _execute_nodes(ctx, body, script_block.span.file, in_loop=False)

        # Handle WHILE/UNTIL loops
        # Convert deferred vars once — node.loop_condition is immutable after parsing
        condition = ""
        if node.loop_type is not None and node.loop_condition is not None:
            condition = _convert_deferred_vars(node.loop_condition)

        if node.loop_type == "WHILE":
            while True:
                effective_locals = _stack_localvars(ctx)
                expanded = substitute_vars(condition, effective_locals, ctx=ctx)
                if not xcmd_test(expanded):
                    break
                frame.iteration += 1
                try:
                    _run_body()
                except _BreakLoop:
                    break
        elif node.loop_type == "UNTIL":
            while True:
                frame.iteration += 1
                try:
                    _run_body()
                except _BreakLoop:
                    break
                effective_locals = _stack_localvars(ctx)
                expanded = substitute_vars(condition, effective_locals, ctx=ctx)
                if xcmd_test(expanded):
                    break
        else:
            try:
                _run_body()
            except _BreakLoop as exc:
                raise ErrInfo(
                    type="cmd",
                    other_msg=f"BREAK metacommand inside SCRIPT '{script_block.name}' but not inside a LOOP.",
                ) from exc
    finally:
        _pop_frame(ctx)


def _execute_include_native(
    ctx: RuntimeContext,
    node: IncludeDirective,
    localvars: SubVarSet | None = None,
) -> None:
    """Parse an INCLUDE'd file with the AST parser and execute it natively.

    Handles tilde expansion, IF EXISTS, logging, and circular-include
    detection via ``ctx.include_chain``.
    """
    from execsql.script.parser import parse_script
    from execsql.utils.errors import file_size_date

    # Substitute variables in the target path
    effective_locals = _stack_localvars(ctx) or localvars
    target = substitute_vars(node.target, effective_locals, ctx=ctx).strip()

    # Strip surrounding quotes — the AST parser captures the full target
    # including any quotes, but the legacy dispatch regex stripped them.
    if len(target) >= 2 and target[0] in ('"', "'") and target[-1] == target[0]:
        target = target[1:-1]

    # Tilde expansion (matches x_include legacy handler)
    if len(target) > 1 and target[0] == "~" and target[1] == os.sep:
        target = str(Path.home() / target[2:])

    # Optional containment: when conf.include_root is set, the resolved
    # INCLUDE / EXECUTE SCRIPT target must live under that root.
    include_root = getattr(ctx.conf, "include_root", None) if hasattr(ctx, "conf") else None
    if include_root is None:
        import execsql.state as _state

        include_root = getattr(_state.conf, "include_root", None)
    if include_root:
        from execsql.utils.fileio import safe_output_path

        target = safe_output_path(target, include_root)

    target_path = Path(target)

    # IF EXISTS handling
    if node.if_exists:
        if not target_path.is_file():
            return
    else:
        if not target_path.is_file():
            raise ErrInfo(type="error", other_msg=f"File {target} does not exist.")

    # Resolve to absolute for consistent circular-include detection
    resolved = str(target_path.resolve())

    # Circular include detection
    if resolved in ctx.include_chain:
        chain = " → ".join(ctx.include_chain + [resolved])
        raise ErrInfo(
            type="error",
            other_msg=f"Circular INCLUDE detected: {chain}",
        )

    # Log the include (matching legacy read_sqlfile behavior)
    if ctx.exec_log:
        sz, dt = file_size_date(target)
        ctx.exec_log.log_status_info(f"Reading script file {target} (size: {sz}; date: {dt})")

    # Parse with AST parser
    encoding = ctx.conf.script_encoding if ctx.conf is not None else "utf-8"
    included_tree = parse_script(target, encoding=encoding)

    # Pre-register SCRIPT blocks in the included file so forward references work.
    _pre_register_scripts(ctx, included_tree.body)

    # Execute with include-chain tracking
    from execsql.state import ExecFrame

    ctx.include_chain.append(resolved)
    _push_block_frame(
        ctx,
        ExecFrame(kind="include", label=Path(resolved).name, source=resolved, line=1),
    )
    try:
        _execute_nodes(ctx, included_tree.body, included_tree.source, localvars)
    finally:
        ctx.ast_exec_stack.pop()
        ctx.include_chain.pop()


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

    def current_script_line(self) -> tuple[str, int]:
        return (self.source, self.line_no)

    def commandline(self) -> str:
        return cast(str, self.command.commandline())


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

    # Activate this context so all _state.foo accesses in metacommand
    # handlers, database adapters, and other legacy code resolve against
    # it.  This gives full isolation without modifying 200+ handler
    # function signatures.
    with active_context(ctx):
        ctx.ast_scripts.clear()
        ctx.include_chain.clear()
        ctx.ast_exec_stack.clear()
        ctx.last_command = None
        # Seed the include chain with the main script to catch self-includes.
        if script.source != "<inline>":
            try:
                ctx.include_chain.append(str(Path(script.source).resolve()))
            except (OSError, ValueError):
                ctx.include_chain.append(script.source)
        set_static_system_vars(ctx)
        # Pre-register all SCRIPT blocks so forward references work.
        # The legacy engine registered scripts at parse time (two-pass);
        # the AST executor must do an explicit pre-scan.
        _pre_register_scripts(ctx, script.body)
        # Push a root <main> scope frame so the AST exec stack is never
        # empty during execution.  This ensures get_subvarset(),
        # current_script_line(), xf_sub_defined(), the REPL, and every
        # variable-scoping reader works correctly even at the top level.
        _push_frame(ctx, "<main>", script.source, line_no=1, kind="main")
        try:
            _execute_nodes(ctx, script.body, script.source)
        except _BreakLoop as exc:
            raise ErrInfo(
                type="cmd",
                other_msg="BREAK metacommand outside of a LOOP block.",
            ) from exc
        finally:
            _pop_frame(ctx)
