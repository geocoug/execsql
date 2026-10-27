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
from collections.abc import Callable

from execsql.exceptions import ErrInfo, ScriptExit
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
    SourceSpan,
    SqlStatement,
)
from execsql import manifest as _manifest
from execsql.script.control import _roll_back
from execsql.script.parser import substitute_directive
from execsql.script.engine import set_dynamic_system_vars, set_static_system_vars, substitute_vars
from execsql.script.variables import ScriptArgSubVarSet, SubVarSet
from execsql.state import ExecFrame, RuntimeContext, active_context, get_context, xcmd_test
from execsql.utils.errors import exception_desc, exit_now, logged_error, stamp_errinfo

__all__ = ["execute", "execute_input"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Regex for deferred variable conversion: !{$VAR}! → !!$VAR!!
_DEFER_RX = re.compile(r"!\{([$@&~#+]?\w+)\}!")

# Compiled regex to match prefixed variables (for unsubstituted-var warnings)
_VARLIKE = re.compile(r"!![$@&~#]?\w+!!", re.I)


def _warn_unsubstituted(cmd: str) -> None:
    """Log a command that still looks like it holds a variable; print it too if ``write_warnings`` is on."""
    from execsql.utils.errors import write_warning
    from execsql.utils.fileio import redact

    write_warning(f"There is a potential un-substituted variable in the command\n     {redact(cmd)}")


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


def _condition_holds(
    ctx: RuntimeContext,
    command: str,
    span: SourceSpan,
    condition: str,
    modifiers: list[ConditionModifier] | None = None,
) -> bool:
    """Evaluate the condition of IF, ELSEIF, LOOP or EXECUTE SCRIPT … WHILE / UNTIL, with its ANDIF / ORIF modifiers.

    Short-circuits ANDIF (stops on first False) and ORIF (stops on first True)
    so that patterns like ``IF (sub_defined(x)) ANDIF (not sub_empty(x))``
    don't evaluate ``sub_empty`` when ``x`` is undefined.

    *command* is the metacommand as written, on the line *span* starts; an
    error is reported there, or on the ANDIF / ORIF that raised it.
    """
    effective_locals = _stack_localvars(ctx)
    result = _test(ctx, command, span, condition, effective_locals)
    for mod in modifiers or []:
        # Short-circuit: AND with False can't become True,
        # OR with True can't become False.
        if (mod.kind == "AND" and not result) or (mod.kind == "OR" and result):
            continue
        keyword = "ANDIF" if mod.kind == "AND" else "ORIF"
        result = _test(ctx, f"{keyword} ({mod.condition})", mod.span, mod.condition, effective_locals)
    return result


def _test(
    ctx: RuntimeContext,
    command: str,
    span: SourceSpan,
    condition: str,
    localvars: SubVarSet | None,
) -> bool:
    """One condition of *command*: its value.

    A condition that cannot be evaluated stops the run.  Its error is raised
    with the line and text of *command*, which may be an ELSEIF, ANDIF or
    ORIF rather than the statement on record, or a loop condition evaluated
    after its body.
    """
    try:
        return xcmd_test(substitute_vars(condition, localvars, ctx=ctx))
    except Exception as exc:
        e = _as_errinfo(exc)
        if e.script_file is None:
            e.script_file, e.script_line_no = span.file, span.start_line
            e.cmd, e.cmdtype = command, "cmd"
        # The run stops, except at a BREAKPOINT prompt, which carries on:
        # a test that failed in the database (HASROWS) has rolled back the
        # connection, so the batch must not commit.
        _fail_open_batches(ctx, span.file, span.start_line)
        if e is exc:
            raise
        raise e from exc


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
        _warn_unsubstituted(cmd)
    e = None
    result = None
    try:
        db = dbs.current()
        if conf.log_sql and ctx.exec_log:
            ctx.exec_log.log_sql_query(cmd, db.name(), line_no)
        if ctx.prompt_input is not None:
            result = db.execute(cmd, fetch=True)
        else:
            db.execute(cmd)
        if commit:
            db.commit()
    except Exception as exc:
        e = _as_errinfo(exc)
    except _CONTROL_FLOW:
        raise
    except BaseException:
        # Interrupted (Ctrl-C) after the statement ran: treat it as a failed
        # statement, or the next commit stores it -- a BREAKPOINT prompt
        # carries on, and execsql.run()'s caller keeps the connection.
        try:
            _record_interrupt(ctx, cmd, source, line_no, sql=True)
        finally:
            dbs.current().rollback()
        raise
    if e:
        _sql_failed(ctx, e, cmd, source, line_no)
        return
    subvars.add_substitution("$LAST_SQL", cmd)
    if ctx.prompt_input is not None:
        ctx.prompt_input(result)


def _record_interrupt(ctx: RuntimeContext, cmd: str, source: str, line_no: int, *, sql: bool) -> None:
    """Record an interrupted statement or metacommand as a failed one, without halting.

    The interrupt itself ends the run, or the BREAKPOINT prompt that caught
    it reads the next input.  The open batches fail first, so a second
    interrupt during the rollback that follows cannot let one commit.
    """
    assert ctx.status is not None
    assert ctx.subvars is not None
    _fail_open_batches(ctx, source, line_no)
    if sql:
        ctx.status.sql_error = True
    else:
        ctx.status.metacommand_error = True
    ctx.subvars.add_substitution("$LAST_ERROR", cmd)
    ctx.subvars.add_substitution("$ERROR_MESSAGE", "Interrupted.")
    if ctx.exec_log is not None:
        kind = "SQL statement" if sql else "Metacommand"
        ctx.exec_log.log_status_info(f"{kind} interrupted on line {line_no} of {source}.")


def _sql_failed(ctx: RuntimeContext, e: ErrInfo, cmd: str, source: str, line_no: int) -> None:
    """Report an SQL error: halt under ERROR_HALT ON, else record it and carry on.

    Sets ``$LAST_ERROR`` to *cmd*, ``$ERROR_MESSAGE`` and ``SQL_ERROR()``.
    """
    assert ctx.status is not None
    assert ctx.subvars is not None
    stamp_errinfo(e)
    ctx.subvars.add_substitution("$LAST_ERROR", cmd)
    ctx.subvars.add_substitution("$ERROR_MESSAGE", e.errmsg())
    ctx.status.sql_error = True
    if ctx.exec_log is not None:
        ctx.exec_log.log_status_info(f"SQL error: {logged_error(e)}")
    _fail_open_batches(ctx, source, line_no)
    if ctx.status.halt_on_err:
        exit_now(1, e)
    ctx.status.error_history.append((source, line_no, cmd, e.errmsg()))


# ---------------------------------------------------------------------------
# Metacommand execution
# ---------------------------------------------------------------------------


def _as_errinfo(exc: Exception) -> ErrInfo:
    """*exc* as an :class:`ErrInfo`: itself if it is one, else an exception report.

    The report keeps *exc* as its ``__cause__``: the driver's or parser's own
    message, which a prompt shows.  Call it in the ``except`` clause, where
    :func:`exception_desc` can still see the exception.
    """
    if isinstance(exc, ErrInfo):
        return exc
    e = ErrInfo(type="exception", exception_msg=exception_desc())
    e.__cause__ = exc
    return e


def _fail_open_batches(ctx: RuntimeContext, source: str, line_no: int) -> None:
    """Keep every open batch from committing after an error inside it.

    Whatever failed (a statement, a metacommand, or SQL a metacommand ran),
    the batch is not committed: a database error may already have rolled
    back the batch's earlier work, and execsql cannot tell from here whether
    it did.
    """
    assert ctx.status is not None
    if ctx.status.batch.in_batch():
        ctx.status.batch.fail_enclosing(f"an error on line {line_no} of {source}")


def _metacommand_failed(
    ctx: RuntimeContext,
    cmd: str,
    e: ErrInfo,
    source: str,
    line_no: int,
    *,
    always_halt: bool = False,
) -> None:
    """Record a failed metacommand; stop the run if METACOMMAND_ERROR_HALT is on, or *always_halt*.

    With it off the script carries on, and ``METACOMMAND_ERROR()``,
    ``$LAST_ERROR`` and ``$ERROR_MESSAGE`` say what failed.
    """
    status = ctx.status
    subvars = ctx.subvars
    assert status is not None
    assert subvars is not None
    stamp_errinfo(e)
    status.metacommand_error = True
    subvars.add_substitution("$LAST_ERROR", cmd)
    subvars.add_substitution("$ERROR_MESSAGE", e.errmsg())
    if ctx.exec_log is not None:
        ctx.exec_log.log_status_info(f"Metacommand error: {logged_error(e)}")
    _fail_open_batches(ctx, source, line_no)
    if status.halt_on_metacommand_err or always_halt:
        exit_now(1, e)
    status.error_history.append((source, line_no, cmd, e.errmsg()))


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
        _warn_unsubstituted(cmd)
    e = None
    try:
        applies, result = metacommandlist.eval(cmd)
        if applies:
            if (manifest := _manifest.current()) is not None:
                manifest.record_metacommand(cmd, source, line_no, metacommandlist)
            return result
    except Exception as exc:
        e = _as_errinfo(exc)
    except _CONTROL_FLOW:
        raise
    except BaseException:
        # Interrupted (Ctrl-C): what the metacommand wrote (EXECUTE, IMPORT,
        # COPY, PG_UPSERT) may wait for a commit that never came.  Each
        # statement is committed as it runs, so on a connection with
        # autocommit on that is all that is pending; under AUTOCOMMIT OFF it
        # joins what the script holds, which the script decides.
        try:
            _record_interrupt(ctx, cmd, source, line_no, sql=False)
        finally:
            assert ctx.dbs is not None
            _roll_back([ctx.dbs.aliased_as(alias) for alias in ctx.dbs.aliases()])
        raise
    if e:
        _metacommand_failed(ctx, cmd, e, source, line_no)
        if (manifest := _manifest.current()) is not None:
            manifest.record_metacommand(cmd, source, line_no, metacommandlist)
        return None
    # No handler matched — truly unknown metacommand
    status.metacommand_error = True
    _fail_open_batches(ctx, source, line_no)
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
        # Deduplicate trailing semicolons
        text = re.sub(r"\s*;(\s*;\s*)+$", ";", text)
        ctx.last_command = ExecutingStatement(node)
        _exec_sql(
            ctx,
            text,
            node.span.file,
            node.span.start_line,
            localvars,
            commit=not ctx.status.batch.in_batch(),
        )
        if (manifest := _manifest.current()) is not None:
            manifest.record_sql()

    elif isinstance(node, MetaCommandStatement):
        command = node.command
        if in_loop:
            command = _convert_deferred_vars(command)
        # Substitute once: the same expanded text is used for BREAK detection
        # and dispatch.  Calling substitute_vars twice would double-increment
        # !!$COUNTER_N!! and re-roll !!$RANDOM!!/!!$UUID!! references.
        effective_locals = _stack_localvars(ctx) or localvars
        expanded = substitute_vars(command, effective_locals, ctx=ctx)
        ctx.last_command = ExecutingStatement(node)
        if not _BREAK_RX.match(expanded):
            _exec_metacommand(ctx, expanded, node.span.file, node.span.start_line)
        elif _break_has_target(ctx):
            raise _BreakLoop
        else:
            _metacommand_failed(
                ctx,
                expanded,
                ErrInfo(
                    type="cmd",
                    other_msg="BREAK has nothing to leave: it is not inside a LOOP, SCRIPT or included file.",
                ),
                node.span.file,
                node.span.start_line,
            )

    elif isinstance(node, IfBlock):
        ctx.last_command = ExecutingStatement(node)
        _execute_if(ctx, node, localvars, in_loop=in_loop)

    elif isinstance(node, LoopBlock):
        ctx.last_command = ExecutingStatement(node)
        _execute_loop(ctx, node, localvars)

    elif isinstance(node, BatchBlock):
        ctx.last_command = ExecutingStatement(node)
        _execute_batch(ctx, node, localvars, in_loop=in_loop)

    elif isinstance(node, ScriptBlock):
        ctx.last_command = ExecutingStatement(node)
        _register_script_block(ctx, node)

    elif isinstance(node, SqlBlock):
        ctx.last_command = ExecutingStatement(node)
        _execute_sql_block(ctx, node, localvars, in_loop=in_loop)

    elif isinstance(node, IncludeDirective):
        ctx.last_command = ExecutingStatement(node)
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

    if _condition_holds(ctx, node.command, node.span, node.condition, node.condition_modifiers):
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
        if _condition_holds(ctx, clause.command, clause.span, clause.condition, clause.condition_modifiers):
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
                ctx.last_command = ExecutingStatement(node)
                if not _condition_holds(ctx, node.command, node.span, condition):
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
                ctx.last_command = ExecutingStatement(node)
                if _condition_holds(ctx, node.command, node.span, condition):
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
    """Execute a BEGIN BATCH / END BATCH block.

    Reaching END BATCH commits the batch; a commit that fails is an SQL error
    on the END BATCH line, after the batch's uncommitted databases are rolled
    back, and every enclosing batch then rolls back at its own END BATCH
    instead of committing. Leaving it any other way (BREAK,
    an error, HALT) abandons it: see
    :meth:`~execsql.script.control.BatchLevels.abandon_batch` for when that
    rolls back and when an enclosing batch takes the statements over.  A
    halt usually gets there first: :func:`~execsql.utils.errors.exit_now`
    abandons every open batch before an ON ERROR_HALT script runs, so
    nothing is left to do here.
    """
    from execsql.state import ExecFrame

    status = ctx.status
    assert status is not None
    status.batch.new_batch()
    _push_block_frame(
        ctx,
        ExecFrame(kind="batch", label="", source=node.span.file, line=node.span.start_line),
    )
    completed = False
    try:
        _execute_nodes(ctx, node.body, node.span.file, localvars, in_loop=in_loop)
        completed = True
    finally:
        ctx.ast_exec_stack.pop()
        if status.batch.in_batch() and not completed:
            status.batch.abandon_batch()
    if status.batch.in_batch():
        end_line = node.span.effective_end_line
        ctx.last_command = ExecutingStatement(
            MetaCommandStatement(span=SourceSpan(node.span.file, end_line), command="END BATCH"),
        )
        failure = status.batch.failure()
        if failure is not None:
            status.batch.abandon_batch()
            e = ErrInfo(type="error", other_msg=f"The batch was not committed: {failure}.")
            _sql_failed(ctx, e, "END BATCH", node.span.file, end_line)
            return
        # The commit is the batch's last SQL: SQL_ERROR() right after END
        # BATCH says whether it failed, as after any statement.
        status.sql_error = False
        try:
            status.batch.end_batch()
        except Exception as exc:
            # end_batch has rolled back what it had not committed, which can
            # include an enclosing batch's statements on a shared connection;
            # _sql_failed keeps that batch from committing the rest.
            _sql_failed(ctx, _as_errinfo(exc), "END BATCH", node.span.file, end_line)
        except _CONTROL_FLOW:
            raise
        except BaseException:
            # Interrupted during the commit: end_batch has rolled back as for
            # a failed one, and the enclosing batches must not commit the rest
            # (a BREAKPOINT prompt carries on after Ctrl-C).
            _record_interrupt(ctx, "END BATCH", node.span.file, end_line, sql=True)
            raise


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
    """Run an INCLUDE or EXECUTE SCRIPT written in the script.

    Variables in its file, script name and arguments are substituted once,
    as in any other metacommand, so ``!!$COUNTER_1!!`` counts once and
    ``$LAST_ERROR`` holds the text that ran.  An EXECUTE SCRIPT ``WHILE`` /
    ``UNTIL`` condition is substituted on each pass instead.
    """
    effective_locals = _stack_localvars(ctx) or localvars
    directive = substitute_directive(node, lambda text: substitute_vars(text, effective_locals, ctx=ctx))
    _run_directive(ctx, directive, localvars)


def _run_directive(
    ctx: RuntimeContext,
    node: IncludeDirective,
    localvars: SubVarSet | None = None,
) -> None:
    """Run an INCLUDE or EXECUTE SCRIPT whose variables have been substituted.

    **INCLUDE** parses the target file with the AST parser and executes it
    with circular-include detection.  **EXECUTE SCRIPT** runs a SCRIPT
    registered in ``ctx.ast_scripts`` with its arguments in a local variable
    overlay, once or in a WHILE / UNTIL loop.

    The INCLUDE or EXECUTE SCRIPT failing itself (no such file or script, a
    missing argument) is a metacommand error; see :func:`_directive_failed`.
    """
    if (manifest := _manifest.current()) is not None:
        assert ctx.metacommandlist is not None
        manifest.record_metacommand(node.command, node.span.file, node.span.start_line, ctx.metacommandlist)

    if not node.is_execute_script:
        _execute_include_native(ctx, node, localvars)
        return

    target = node.target.strip().lower()
    script_block = ctx.ast_scripts.get(target)
    if script_block is None:
        # IF EXISTS silently skips a SCRIPT that is not defined.
        if not node.if_exists:
            _directive_failed(ctx, node, ErrInfo("cmd", other_msg=f"There is no SCRIPT named {node.target.strip()}."))
        return
    try:
        paramvals = _script_args(node, script_block)
    except ErrInfo as e:
        _directive_failed(ctx, node, e)
        return
    _execute_script_native(ctx, node, script_block, paramvals)


def _directive_failed(ctx: RuntimeContext, node: IncludeDirective, e: ErrInfo) -> None:
    """INCLUDE or EXECUTE SCRIPT itself failed (no such file or script, a missing argument): a metacommand error.

    Errors raised by the statements an included file or script runs are
    theirs, not the directive's, and are handled where they happen.
    """
    _metacommand_failed(ctx, node.command, e, node.span.file, node.span.start_line)


def _script_args(node: IncludeDirective, script_block: ScriptBlock) -> ScriptArgSubVarSet | None:
    """The arguments an EXECUTE SCRIPT passes to *script_block*, with defaults for those it leaves out.

    ``node.arguments`` must already be substituted.  Raises :class:`ErrInfo`
    when a required parameter has no argument.
    """
    from execsql.utils.strings import wo_quotes

    if node.arguments is not None:
        args_rx = re.compile(
            r'(?P<param>#?\w+)\s*=\s*(?P<arg>(?:(?:[^"\'\[][^,\)]*)|(?:"[^"]*")|(?:\'[^\']*\')|(?:\[[^\]]*\])))',
            re.I,
        )
        all_args = re.findall(args_rx, node.arguments)
        all_cleaned_args = [(ae[0], wo_quotes(ae[1])) for ae in all_args]
        all_prepared_args = [(ae[0] if ae[0][0] == "#" else "#" + ae[0], ae[1]) for ae in all_cleaned_args]
        paramvals = ScriptArgSubVarSet()
        for param, arg in all_prepared_args:
            paramvals.add_substitution(param, arg)
        passed_names = [p[0].lstrip("#") for p in all_prepared_args]
    else:
        if script_block.param_defs is None:
            return None
        paramvals = ScriptArgSubVarSet()
        passed_names = []

    # Validate parameter names match — with default parameter support
    if script_block.param_defs is not None:
        missing = [p.name for p in script_block.param_defs if p.required and p.name not in passed_names]
        if missing:
            raise ErrInfo(
                "error",
                other_msg=f"Missing required parameter(s) ({', '.join(missing)}) in call to {script_block.name}.",
            )
        # Inject defaults for optional params not provided
        for pdef in script_block.param_defs:
            if pdef.default is not None and pdef.name not in passed_names:
                paramvals.add_substitution(f"#{pdef.name}", pdef.default)
    return paramvals


def _execute_script_native(
    ctx: RuntimeContext,
    node: IncludeDirective,
    script_block: ScriptBlock,
    paramvals: ScriptArgSubVarSet | None,
) -> None:
    """Execute a SCRIPT block natively through the AST executor.

    *paramvals* are its arguments, from :func:`_script_args`.

    Pushes a SCRIPT-kind :class:`~execsql.state.ExecFrame` onto
    ``ctx.ast_exec_stack`` so that metacommand handlers (``x_sub``,
    ``x_rm_sub``, ``xf_sub_defined``, prompt handlers, etc.) can access
    ``~`` local variables and ``#`` script arguments via
    ``ctx.current_localvars()`` / ``ctx.current_paramvals()``. The frame
    is popped on exit (including on error) via ``try/finally``.
    """
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
                ctx.last_command = ExecutingStatement(node)
                if not _condition_holds(ctx, node.command, node.span, condition):
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
                ctx.last_command = ExecutingStatement(node)
                if _condition_holds(ctx, node.command, node.span, condition):
                    break
        else:
            try:
                _run_body()
            except _BreakLoop:
                pass  # BREAK outside a LOOP in the script returns from it
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
    try:
        loaded = _load_include(ctx, node)
    except _OutsideIncludeRoot as refused:
        # A security boundary, not a script error to carry on from: the run
        # stops whatever METACOMMAND_ERROR_HALT says.
        _metacommand_failed(ctx, node.command, refused.errinfo, node.span.file, node.span.start_line, always_halt=True)
        return
    except Exception as exc:
        _directive_failed(ctx, node, _as_errinfo(exc))
        return
    if loaded is None:
        return
    resolved, included_tree = loaded

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
    except _BreakLoop:
        pass  # BREAK outside a LOOP in the file leaves it
    finally:
        ctx.ast_exec_stack.pop()
        ctx.include_chain.pop()


class _OutsideIncludeRoot(Exception):
    """An INCLUDE's file is outside ``include_root``; *errinfo* says where it resolved."""

    def __init__(self, errinfo: ErrInfo) -> None:
        super().__init__(str(errinfo))
        self.errinfo = errinfo


def _load_include(
    ctx: RuntimeContext,
    node: IncludeDirective,
) -> tuple[str, Any] | None:
    """Find and parse the file an INCLUDE names: ``(resolved path, tree)``, or ``None`` to skip it (IF EXISTS).

    Raises :class:`_OutsideIncludeRoot` for a file outside ``include_root``,
    and :class:`ErrInfo` when the INCLUDE itself fails: no such file, a
    circular include, or a file that does not parse.
    """
    from execsql.script.parser import parse_script
    from execsql.utils.errors import file_size_date

    target = node.target
    # Tilde expansion (matches the monolith's x_include)
    if len(target) > 1 and target[0] == "~" and target[1] == os.sep:
        target = str(Path.home() / target[2:])

    # Optional containment: when conf.include_root is set, the file must
    # live under that root.
    include_root = getattr(ctx.conf, "include_root", None) if hasattr(ctx, "conf") else None
    if include_root is None:
        import execsql.state as _state

        include_root = getattr(_state.conf, "include_root", None)
    if include_root:
        from execsql.utils.fileio import safe_output_path

        try:
            target = safe_output_path(target, include_root)
        except ErrInfo as e:
            raise _OutsideIncludeRoot(e) from e

    target_path = Path(target)

    # IF EXISTS handling
    if node.if_exists:
        if not target_path.is_file():
            return None
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
    if (manifest := _manifest.current()) is not None:
        manifest.record_include(target, node.span.file, node.span.start_line)
    return resolved, included_tree


# ---------------------------------------------------------------------------
# BREAK support
# ---------------------------------------------------------------------------


class _BreakLoop(BaseException):
    """Raised by BREAK to leave the innermost LOOP, SCRIPT or included file.

    A ``BaseException``, like ``KeyboardInterrupt``, so the ``except
    Exception`` handlers it may pass on its way to the loop leave it alone:
    a BREAK typed at a BREAKPOINT prompt travels out through the BREAKPOINT
    metacommand's handler.
    """


# BaseExceptions that are execsql's own control flow, not an interrupt:
# ScriptExit (HALT, a halting error, a cancelled PROMPT or dialog, ``.quit``)
# and _BreakLoop (BREAK).  Any other BaseException -- KeyboardInterrupt, or a
# plain SystemExit from a signal handler -- is an interrupt.
_CONTROL_FLOW = (ScriptExit, _BreakLoop)


def _break_has_target(ctx: RuntimeContext) -> bool:
    """Whether a BREAK at the current statement has something to leave.

    BREAK leaves the innermost LOOP, SCRIPT or included file (a SCRIPT that
    ``EXECUTE SCRIPT … WHILE`` / ``UNTIL`` repeats stops repeating); in the main
    script outside all of them there is nothing to leave.

    Each kind listed here must have a runner that catches ``_BreakLoop``:
    ``_execute_loop``, ``_execute_script_native`` and
    ``_execute_include_native``.  A ``_BreakLoop`` nobody catches would end
    the run as an uncaught BaseException.
    """
    for frame in reversed(ctx.ast_exec_stack):
        if frame.kind in ("loop_while", "loop_until", "script", "include"):
            return True
        if frame.kind == "main":
            return False
    return False


_BREAK_RX = re.compile(r"^\s*BREAK\s*$", re.I)


# ---------------------------------------------------------------------------
# The statement the executor is currently on
# ---------------------------------------------------------------------------


class _StatementText:
    """The text of one statement, in the two spellings its readers expect.

    ``statement`` is the raw text; ``commandline()`` is the text as it
    appeared in the source, so a metacommand gets its ``-- !x!`` marker back.
    """

    __slots__ = ("statement", "_prefix")

    def __init__(self, statement: str, prefix: str = "") -> None:
        self.statement = statement
        self._prefix = prefix

    def commandline(self) -> str:
        return self._prefix + self.statement


class ExecutingStatement:
    """Where the executor is, as ``ctx.last_command`` exposes it.

    The AST node is the single representation of a statement.  This wraps one
    rather than copying fields out of it, so there is nothing to keep in sync
    and no second source of truth about what is executing.  Error reporting
    (:mod:`execsql.utils.errors`), the debug REPL, and ``api.run()`` read
    its attributes; everything is derived from ``node`` on access, so
    constructing one costs a single small object per statement rather than
    the two classes the previous shim built each time.
    """

    __slots__ = ("node",)

    def __init__(self, node: Node) -> None:
        self.node = node

    @property
    def source(self) -> str:
        return self.node.span.file

    @property
    def line_no(self) -> int:
        return self.node.span.start_line

    @property
    def command_type(self) -> str:
        return "sql" if isinstance(self.node, SqlStatement) else "cmd"

    @property
    def command(self) -> _StatementText:
        node = self.node
        if isinstance(node, SqlStatement):
            return _StatementText(node.text)
        command = getattr(node, "command", "")
        return _StatementText(command, "-- !x! " if command else "")

    def __repr__(self) -> str:
        return f"ExecutingStatement({self.source}:{self.line_no}, {self.command_type})"


# ---------------------------------------------------------------------------
# Node type/text helpers for profiling
# ---------------------------------------------------------------------------


def _node_cmd_type(node: Node) -> str:
    if isinstance(node, SqlStatement):
        return "sql"
    return "cmd"


def _node_cmd_text(node: Node) -> str:
    return ExecutingStatement(node).command.commandline() or repr(node)


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
        finally:
            _pop_frame(ctx)


# ---------------------------------------------------------------------------
# Input typed at a prompt
# ---------------------------------------------------------------------------


def execute_input(
    script: Script,
    show: Callable[[tuple[list[str], list] | None], None],
    *,
    ctx: RuntimeContext | None = None,
) -> None:
    """Run input typed at a BREAKPOINT prompt as the next lines of the paused script.

    The input runs as if it were written where the script paused: in its
    variable scope, its batch and its loop, so a BREAK leaves that loop
    (or the SCRIPT or included file it paused in).
    Unlike :func:`execute`, nothing is reset.

    *show* receives the result of each SQL statement run.  An error that
    would halt the run is raised to the caller instead (see ``exit_now``).
    The paused script's current statement is restored afterwards, so the
    debug REPL's ``.where`` still shows it.
    """
    if ctx is None:
        ctx = get_context()
    with active_context(ctx):
        _pre_register_scripts(ctx, script.body)
        last_command, prompt_input = ctx.last_command, ctx.prompt_input
        ctx.prompt_input = show
        try:
            _execute_nodes(ctx, script.body, script.source)
        except _CONTROL_FLOW:
            raise
        except BaseException:
            # The prompt catches Ctrl-C and the script carries on, so whatever
            # the interrupt stopped (a statement, a condition's query, END
            # BATCH) may have left a batch's work half done or rolled back:
            # no open batch may commit.
            assert ctx.status is not None
            ctx.status.batch.fail_enclosing(f"an interrupt of input typed at {script.source}")
            raise
        finally:
            ctx.prompt_input = prompt_input
            ctx.last_command = last_command
