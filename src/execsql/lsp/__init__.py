"""Language Server Protocol (LSP) implementation for execsql.

Provides IDE features for ``.sql`` files containing execsql metacommands:
diagnostics (live lint), hover documentation, go-to-definition,
autocompletion, and document symbols.

Start the server::

    python -m execsql.lsp          # stdio transport (default)
    python -m execsql.lsp --tcp    # TCP transport (for debugging)

Requires ``pygls``: ``pip install execsql2[lsp]``
"""

from __future__ import annotations

__all__ = ["start_server"]


def start_server(transport: str = "stdio") -> None:
    """Start the execsql language server.

    Args:
        transport: ``"stdio"`` (default) or ``"tcp"``.
    """
    from execsql.lsp.server import create_server

    server = create_server()
    if transport == "tcp":
        server.start_tcp("127.0.0.1", 2087)
    else:
        server.start_io()
