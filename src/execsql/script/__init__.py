from __future__ import annotations

"""
Core script-execution data types and helpers for execsql.

This package re-exports the data structures, dispatch primitives, and AST
machinery that drive execution of execsql ``.sql`` script files. Script
parsing lives in :mod:`execsql.script.parser`; tree-walking execution
lives in :mod:`execsql.script.executor`.

Key classes:

- :class:`BatchLevels` — tracks which databases are used in nested BEGIN/END
  BATCH blocks for commit/rollback handling.
- :class:`CounterVars` — named integer counters (``$COUNTER_N``).
- :class:`SubVarSet` — substitution-variable store covering all sigils
  (no prefix, ``$``, ``&``, ``@``).
- :class:`LocalSubVarSet` / :class:`ScriptArgSubVarSet` — per-script-scope
  variable overlays for ``~`` local and ``#`` argument variables. Stored
  on the active :class:`~execsql.state.ExecFrame` and retrieved via
  ``ctx.current_localvars()`` / ``ctx.current_paramvals()``.
- :class:`MetaCommand` — one entry in the metacommand dispatch table (regex +
  handler function + flags).
- :class:`MetaCommandList` — ordered list of :class:`MetaCommand` entries
  with a keyword index for fast dispatch.
- :class:`SqlStmt` / :class:`MetacommandStmt` / :class:`ScriptCmd` —
  statement wrappers carried in the AST and used by ``ctx.last_command``
  for source-location tracking.
- :class:`ScriptExecSpec` — specification for deferred script execution
  (used by ``ON ERROR_HALT`` / ``ON CANCEL_HALT EXECUTE SCRIPT``).

Key functions:

- :func:`set_system_vars` — populates built-in ``$VARNAME`` system variables
  (calls the static + dynamic helpers).
- :func:`substitute_vars` — performs ``!!$VAR!!`` / ``!'!var!'!`` /
  ``!"!var!"!`` / ``!{$var}!`` expansion.
- :func:`current_script_line` — returns the ``(file, line_no)`` of the
  currently executing command.
- :func:`parse_script` / :func:`parse_string` — produce a
  :class:`~execsql.script.ast.Script` AST tree from a file or string,
  consumed by :func:`execsql.script.executor.execute`.
"""

from execsql.script.control import BatchLevels
from execsql.script.engine import (
    MetaCommand,
    MetaCommandList,
    MetacommandStmt,
    ScriptCmd,
    ScriptExecSpec,
    SqlStmt,
    current_script_line,
    set_dynamic_system_vars,
    set_static_system_vars,
    set_system_vars,
    substitute_vars,
)
from execsql.script.ast import (
    BatchBlock,
    Comment,
    ConditionModifier,
    ElseIfClause,
    IfBlock,
    IncludeDirective,
    LoopBlock,
    MetaCommandStatement as AstMetaCommand,
    Node,
    Script,
    ScriptBlock,
    SourceSpan,
    SqlBlock,
    SqlStatement as AstSqlStatement,
    format_tree,
)
from execsql.script.parser import parse_script, parse_string
from execsql.script.variables import CounterVars, LocalSubVarSet, ScriptArgSubVarSet, SubVarSet

__all__ = [
    "BatchLevels",
    "CounterVars",
    "SubVarSet",
    "LocalSubVarSet",
    "ScriptArgSubVarSet",
    "MetaCommand",
    "MetaCommandList",
    "SqlStmt",
    "MetacommandStmt",
    "ScriptCmd",
    "ScriptExecSpec",
    "set_dynamic_system_vars",
    "set_static_system_vars",
    "set_system_vars",
    "substitute_vars",
    "current_script_line",
    # AST nodes and parser
    "Node",
    "SourceSpan",
    "AstSqlStatement",
    "AstMetaCommand",
    "Comment",
    "ConditionModifier",
    "ElseIfClause",
    "IfBlock",
    "LoopBlock",
    "BatchBlock",
    "ScriptBlock",
    "SqlBlock",
    "IncludeDirective",
    "Script",
    "format_tree",
    "parse_script",
    "parse_string",
]
