"""One ruff version everywhere.

``just lint`` / ``just format`` run the ruff in ``uv.lock``, the pre-commit
hook runs its pinned ``rev``, and the CI ``lint`` job installs that same
``rev``.  If the two pins drift, the same file can pass locally and fail in
CI, or the reverse.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _locked_version(name: str) -> str:
    # A regex rather than tomllib, which Python 3.10 lacks.
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    m = re.search(rf'^name = "{re.escape(name)}"\nversion = "([^"]+)"', lock, re.MULTILINE)
    assert m, f"{name} not found in uv.lock"
    return m.group(1)


def _pre_commit_rev(repo: str) -> str:
    config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    m = re.search(rf"repo: {re.escape(repo)}\s*\n\s*rev: v?([0-9][0-9.]*)", config)
    assert m, f"{repo} not found in .pre-commit-config.yaml"
    return m.group(1)


def test_uv_lock_ruff_matches_the_pre_commit_hook():
    hook = _pre_commit_rev("https://github.com/astral-sh/ruff-pre-commit")
    locked = _locked_version("ruff")
    assert locked == hook, (
        f"uv.lock has ruff {locked} but .pre-commit-config.yaml pins v{hook}; "
        f"run `uv lock --upgrade-package ruff=={hook}`"
    )
