"""Telling a path on this machine from one that names another.

On Windows, checking or opening a path written as ``\\\\host\\share\\...``
(or ``//host/share/...``) makes the OS contact *host* and offer the logged-in
user's credentials.  The static tools (``execsql lint``, ``execsql format``
and the language server) read paths written in scripts and config files
someone else may have written, so they never touch such a path.
"""

from __future__ import annotations

import os

__all__ = ["is_network_path"]

# Read once; tests set it to check the Windows rules on any OS.
_WINDOWS = os.name == "nt"


def is_network_path(path: str | os.PathLike[str]) -> bool:
    """Whether *path*, as written, names another machine or a device.

    On Windows: a UNC path (``\\\\host\\share``, ``//host/share``, either slash)
    or a ``\\\\?\\`` / ``\\\\.\\`` device path.  Elsewhere a leading double
    slash is an ordinary local path, so nothing is.  A relative path is never
    one: it stays on the machine of the file that names it.
    """
    if not _WINDOWS:
        return False
    text = os.fspath(path)
    return len(text) >= 2 and text[0] in "\\/" and text[1] in "\\/"
