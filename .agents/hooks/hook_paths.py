"""Resolve Claude Code and Codex paths, including both sides of moves and deletions."""

import os
import subprocess
from pathlib import Path


def project_dir(payload: dict) -> Path:
    """Prefer Claude's root, otherwise discover Git's root from the session cwd."""
    if root := os.environ.get("CLAUDE_PROJECT_DIR"):
        return Path(root).resolve()
    cwd = Path(payload.get("cwd") or Path.cwd()).resolve()
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    )
    return Path(result.stdout.strip()).resolve()


def edited_paths(payload: dict) -> list[Path]:
    """Return each edit target relative to session cwd; include removed and moved paths."""
    ti = payload.get("tool_input") or {}
    if payload.get("tool_name") == "apply_patch":
        prefixes = ("*** Add File: ", "*** Update File: ", "*** Move to: ", "*** Delete File: ")
        names = [
            line[len(prefix) :]
            for line in (ti.get("command") or "").splitlines()
            for prefix in prefixes
            if line.startswith(prefix)
        ]
    else:
        names = [ti.get("file_path") or ti.get("notebook_path") or ""]
    cwd = Path(payload.get("cwd") or Path.cwd())
    # Keep lexical names too: a symlink must not hide that the record itself is being edited.
    return list(
        dict.fromkeys(
            path for name in names if name for path in (Path(os.path.abspath(cwd / name)), (cwd / name).resolve())
        ),
    )
