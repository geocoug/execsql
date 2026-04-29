"""Documentation provider for the execsql language server.

Parses the metacommands reference documentation (``docs/reference/metacommands.md``)
at startup and provides rich hover content for each metacommand keyword.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

__all__ = ["get_metacommand_doc", "get_all_doc_keywords"]


def _find_docs_dir() -> Path | None:
    """Locate the docs/reference/ directory relative to the package."""
    # Walk up from the package source to find the repo root
    pkg_dir = Path(__file__).resolve().parent.parent  # src/execsql/
    for ancestor in [pkg_dir.parent.parent, pkg_dir.parent, pkg_dir]:
        candidate = ancestor / "docs" / "reference" / "metacommands.md"
        if candidate.exists():
            return candidate
    return None


@lru_cache(maxsize=1)
def _load_docs() -> dict[str, str]:
    """Parse metacommands.md into a keyword → Markdown content dict.

    Each entry contains the heading, syntax blocks, and description text
    (truncated to a reasonable hover length).
    """
    docs_file = _find_docs_dir()
    if docs_file is None:
        return {}

    try:
        text = docs_file.read_text(encoding="utf-8")
    except OSError:
        return {}

    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        # Match ## HEADING or ## HEADING { #anchor }
        m = re.match(r"^## (.+?)(?:\s*\{.*\})?\s*$", line)
        if m:
            # Save previous section
            if current_key is not None:
                sections[current_key] = _format_section(current_key, current_lines)
            current_key = m.group(1).strip()
            current_lines = []
        elif current_key is not None:
            current_lines.append(line)

    # Save last section
    if current_key is not None:
        sections[current_key] = _format_section(current_key, current_lines)

    return sections


def _format_section(heading: str, lines: list[str]) -> str:
    """Format a documentation section for hover display.

    Includes the full section content. VS Code hover popups handle
    long Markdown content with scrolling.
    """
    result_lines: list[str] = [f"**{heading}**", ""]

    for line in lines:
        # Skip blockquotes (bulleted overview lists) and images
        if line.startswith(">") or line.startswith("!["):
            continue
        result_lines.append(line)

    return "\n".join(result_lines).strip()


def get_metacommand_doc(keyword: str) -> str | None:
    """Return hover documentation for a metacommand keyword.

    Args:
        keyword: The metacommand keyword (e.g., ``"IMPORT"``, ``"IF"``).
            Case-insensitive; tries exact match, then prefix matches.

    Returns:
        Markdown string for hover display, or ``None`` if not found.
    """
    docs = _load_docs()
    if not docs:
        return None

    upper = keyword.upper()

    # Exact match
    for key, content in docs.items():
        if key.upper() == upper:
            return content

    # Find the longest doc key that the command starts with.
    # Sort by key length descending so "PROMPT COMPARE" matches before "PROMPT".
    best_match = None
    best_len = 0
    for key, content in docs.items():
        key_upper = key.upper()
        if upper.startswith(key_upper) and len(key_upper) > best_len:
            best_match = content
            best_len = len(key_upper)

    if best_match:
        return best_match

    # Try matching the first word (e.g., "EXPORT" matches "EXPORT")
    first_word = upper.split(None, 1)[0] if upper else ""
    for key, content in docs.items():
        if key.upper().split(None, 1)[0] == first_word:
            return content

    return None


def get_all_doc_keywords() -> list[str]:
    """Return all documented metacommand keywords."""
    return list(_load_docs().keys())
