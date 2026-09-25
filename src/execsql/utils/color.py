"""The user's color preference, as the environment states it.

One policy for every place execsql writes ANSI itself (the debug REPL, CLI
help): ``NO_COLOR`` (https://no-color.org) or ``EXECSQL_NO_COLOR`` set to any
value turns color off. Whether the stream is a terminal is a separate
question each caller answers for its own stream.
"""

from __future__ import annotations

import os

__all__ = ["color_disabled_by_env"]


def color_disabled_by_env() -> bool:
    """Return True when ``NO_COLOR`` or ``EXECSQL_NO_COLOR`` is set."""
    return os.environ.get("NO_COLOR") is not None or os.environ.get("EXECSQL_NO_COLOR") is not None
