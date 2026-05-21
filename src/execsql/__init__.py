"""
execsql — a maintained fork of the execsql SQL scripting tool.

This package provides the ``execsql`` CLI command (distributed as the
``execsql2`` package on PyPI) and the ``execsql`` importable module.

The top-level package re-exports the public Python API for programmatic
use: :func:`run`, :class:`ScriptResult`, :class:`ScriptError`, and the
:class:`ExecSqlError` exception that :meth:`ScriptResult.raise_on_error`
raises. Internal sub-modules carry the rest of the implementation
(``cli``, ``db``, ``script``, ``metacommands``, etc.).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("execsql2")
except PackageNotFoundError:
    __version__ = "unknown"

from execsql.api import ExecSqlError, ScriptError, ScriptResult, run

__all__ = ["__version__", "run", "ScriptResult", "ScriptError", "ExecSqlError"]
