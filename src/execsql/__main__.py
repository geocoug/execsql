from __future__ import annotations

"""
Entry point for ``python -m execsql``.

Delegates immediately to :func:`execsql.cli.main` so the package can be
invoked directly without going through the installed ``execsql2`` script.
"""

from execsql.cli import _legacy_main

if __name__ == "__main__":
    _legacy_main()
