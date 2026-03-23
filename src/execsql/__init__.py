"""
execsql — a maintained fork of the execsql SQL scripting tool.

This package provides the ``execsql2`` CLI (entry point ``execsql2``) and the
``execsql`` importable module.  The top-level package exposes only the package
version; all public functionality lives in sub-modules.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("execsql2")
except PackageNotFoundError:
    __version__ = "unknown"
