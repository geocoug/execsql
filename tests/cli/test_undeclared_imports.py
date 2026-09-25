"""execsql must not import Click directly.

Typer 0.26 dropped its Click dependency and vendors a copy as
``typer._click``. A fresh ``pip install execsql2`` therefore resolves a Typer
with no ``click`` on the path, and an ``import click`` anywhere on the CLI's
import chain turns every invocation into a ``ModuleNotFoundError``.

The dev environment always has Click (``rich-click`` pulls it in), so no
behavioural test can see this failure. Scanning the source is the only guard
that runs where the bug does not.
"""

from __future__ import annotations

import ast
from pathlib import Path

import execsql

SRC = Path(execsql.__file__).parent


def _click_imports(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue
        if any(name == "click" or name.startswith("click.") for name in names):
            lines.append(node.lineno)
    return lines


def test_no_module_imports_click() -> None:
    offenders = [
        f"{path.relative_to(SRC.parent)}:{line}" for path in sorted(SRC.rglob("*.py")) for line in _click_imports(path)
    ]
    assert not offenders, (
        "click is not a declared dependency and newer Typer does not install it; "
        f"use typer's public API instead: {offenders}"
    )
