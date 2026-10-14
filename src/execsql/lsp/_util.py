"""Small helpers several language-server features share."""

from __future__ import annotations

import re

from lsprotocol import types

__all__ = ["RX_METACOMMAND", "markdown", "span"]

# A metacommand line: the ``-- !x!`` marker (with its spacing) and the command after it.
RX_METACOMMAND = re.compile(r"^(?P<lead>\s*--\s*!x!\s*)(?P<command>.*?)\s*$", re.I)


def span(line: int, start: int, end: int) -> types.Range:
    """The characters *start* to *end* of zero-based *line*."""
    return types.Range(start=types.Position(line=line, character=start), end=types.Position(line=line, character=end))


def markdown(text: str) -> types.MarkupContent:
    return types.MarkupContent(kind=types.MarkupKind.Markdown, value=text)
