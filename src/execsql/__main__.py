"""Entry point for ``python -m execsql``.

Calls :func:`execsql.cli._legacy_main`, so the package runs without the
installed ``execsql`` script.
"""

from __future__ import annotations

from execsql.cli import _legacy_main

if __name__ == "__main__":
    _legacy_main()
