"""Build the shared CLI/library execution plan for configured startup files."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from execsql.script.ast import Script


def prepare_script(script: Script, required: Sequence[str], optional: Sequence[str]) -> Script:
    """Prepend configured includes without changing the parsed main script.

    ConfigData has resolved and ordered the filenames. Required files precede
    optional ones; each configured file runs once, and the main file is not
    included into itself. Normal INCLUDE execution applies containment,
    recursion checks, source reporting and runtime error handling.
    """
    if not required and not optional:
        return script

    from execsql.script.ast import IncludeDirective, Script, SourceSpan

    seen = {str(Path(script.source).resolve())} if script.source != "<inline>" else set()
    includes = []
    for if_exists, filenames in ((False, required), (True, optional)):
        for filename in filenames:
            if filename in seen:
                continue
            seen.add(filename)
            modifier = " IF EXISTS" if if_exists else ""
            includes.append(
                IncludeDirective(
                    span=SourceSpan("<config>", 1),
                    target=filename,
                    if_exists=if_exists,
                    command=f"INCLUDE{modifier} {filename}",
                ),
            )
    return Script(source=script.source, body=[*includes, *script.body]) if includes else script
