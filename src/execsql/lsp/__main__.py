"""Entry point for ``python -m execsql.lsp``."""

from __future__ import annotations

import sys


def main() -> None:
    try:
        import pygls  # noqa: F401
    except ImportError:
        print(
            "The execsql language server requires pygls.\nInstall with: pip install execsql2[lsp]",
            file=sys.stderr,
        )
        sys.exit(1)

    transport = "stdio"
    if "--tcp" in sys.argv:
        transport = "tcp"

    from execsql.lsp import start_server

    start_server(transport=transport)


if __name__ == "__main__":
    main()
