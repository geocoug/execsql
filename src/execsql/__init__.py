"""
execsql — a maintained fork of the execsql SQL scripting tool.

This package provides the ``execsql`` CLI command (distributed as the
``execsql2`` package on PyPI) and the ``execsql`` importable module.
The top-level package exposes only the package version; all public
functionality lives in sub-modules.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("execsql2")
except PackageNotFoundError:
    __version__ = "unknown"

from execsql.api import ExecSqlError, ScriptError, ScriptResult, run

__all__ = ["__version__", "run", "ScriptResult", "ScriptError", "ExecSqlError"]
