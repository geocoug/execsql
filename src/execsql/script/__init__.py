from __future__ import annotations

"""
Core script-execution engine for execsql.

This module contains the data structures and functions that load, parse, and
drive execution of execsql ``.sql`` script files.  It is the heart of the
runtime.

Key classes:

- :class:`BatchLevels` — tracks which databases are used in nested BEGIN/END
  BATCH blocks for commit/rollback handling.
- :class:`IfItem` / :class:`IfLevels` — stack-based IF/ELSE/ENDIF nesting.
- :class:`CounterVars` — named integer counters (``@NAME``).
- :class:`SubVarSet` — global ``!!$VAR!!`` substitution-variable store, plus
  ``&ENV``, ``@COUNTER``, ``~LOCAL``, and ``#ARG`` prefixes.
- :class:`LocalSubVarSet` / :class:`ScriptArgSubVarSet` — per-script-scope
  variable overlays.
- :class:`MetaCommand` — one entry in the metacommand dispatch table (regex +
  handler function + flags).
- :class:`MetaCommandList` — ordered list of :class:`MetaCommand` entries;
  ``get_match()`` finds the first matching entry for a given line.
- :class:`SqlStmt` — wraps a single SQL string; ``run()`` executes it via the
  active database connection.
- :class:`MetacommandStmt` — wraps a metacommand line; ``run()`` dispatches
  through :attr:`execsql.state.metacommandlist`.
- :class:`ScriptCmd` — pairs a statement with its source-file location.
- :class:`CommandList` — ordered list of :class:`ScriptCmd` objects plus an
  execution cursor; ``run_next()`` drives one step of execution.
- :class:`CommandListWhileLoop` / :class:`CommandListUntilLoop` — loop
  variants of :class:`CommandList` that re-evaluate a condition each pass.
- :class:`ScriptFile` — reads and tokenises a ``.sql`` file into
  :class:`ScriptCmd` objects.
- :class:`ScriptExecSpec` — specification for deferred script execution.

Key functions:

- :func:`set_system_vars` — populates built-in ``$VARNAME`` system variables.
- :func:`substitute_vars` — performs ``!!$VAR!!`` and ``!{$var}!`` expansion.
- :func:`runscripts` — central execution loop; pops the top
  :class:`CommandList` from ``_state.commandliststack`` and drives
  ``run_next()`` until the stack is empty.
- :func:`current_script_line` — returns the source location of the currently
  executing command.
- :func:`read_sqlfile` — parses a SQL script file into a new
  :class:`CommandList` and pushes it onto ``_state.commandliststack``.
"""

from execsql.script.control import BatchLevels, IfItem, IfLevels
from execsql.script.engine import (
    CommandList,
    CommandListUntilLoop,
    CommandListWhileLoop,
    MetaCommand,
    MetaCommandList,
    MetacommandStmt,
    ScriptCmd,
    ScriptExecSpec,
    ScriptFile,
    SqlStmt,
    current_script_line,
    read_sqlfile,
    read_sqlstring,
    runscripts,
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
    "IfItem",
    "IfLevels",
    "CounterVars",
    "SubVarSet",
    "LocalSubVarSet",
    "ScriptArgSubVarSet",
    "MetaCommand",
    "MetaCommandList",
    "SqlStmt",
    "MetacommandStmt",
    "ScriptCmd",
    "CommandList",
    "CommandListWhileLoop",
    "CommandListUntilLoop",
    "ScriptFile",
    "ScriptExecSpec",
    "set_dynamic_system_vars",
    "set_static_system_vars",
    "set_system_vars",
    "substitute_vars",
    "runscripts",
    "current_script_line",
    "read_sqlfile",
    "read_sqlstring",
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
