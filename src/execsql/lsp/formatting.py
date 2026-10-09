"""Format Document: ``execsql format`` on the editor's text."""

from __future__ import annotations

from lsprotocol import types

from execsql.format import format_file

__all__ = ["format_document"]


def format_document(
    source: str,
    indent: int = 4,
    use_sql: bool = True,
    leading_comma: bool = False,
    rewrite_sql: bool = False,
) -> list[types.TextEdit]:
    """One edit replacing the whole document with its formatted text; none when it is already formatted.

    The options are ``execsql format``'s, from the ``[format]`` config section.
    """
    formatted = format_file(
        source,
        indent=indent,
        use_sql=use_sql,
        leading_comma=leading_comma,
        rewrite_sql=rewrite_sql,
    )
    if formatted == source:
        return []
    lines = source.splitlines(keepends=True)
    end = types.Position(line=len(lines), character=0)
    if lines and not lines[-1].endswith(("\n", "\r")):
        # LSP counts characters in UTF-16 code units.
        end = types.Position(line=len(lines) - 1, character=len(lines[-1].encode("utf-16-le")) // 2)
    return [types.TextEdit(range=types.Range(start=types.Position(line=0, character=0), end=end), new_text=formatted)]
