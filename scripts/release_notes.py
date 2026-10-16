"""Print one version's section of CHANGELOG.md, the text of its GitHub Release.

Usage: python scripts/release_notes.py X.Y.Z   (a leading "v" is accepted)

The section is everything under ``## [X.Y.Z] - date`` up to the next
release heading or separator line, without the heading itself. Exits 1,
printing nothing to stdout, when the version has no section or the
section is empty, so the release build fails before anything is
published.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def release_notes(version: str, text: str) -> str | None:
    """Return the body of *version*'s section in *text*, or None."""
    version = version.removeprefix("v")
    heading = re.compile(rf"^## \[{re.escape(version)}\](?:\s|$)")
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        return None
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## [") or re.fullmatch(r"_{3,}\s*", line):
            break
        body.append(line)
    notes = "\n".join(body).strip()
    return notes or None


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: release_notes.py X.Y.Z", file=sys.stderr)
        return 2
    notes = release_notes(argv[0], CHANGELOG.read_text(encoding="utf-8"))
    if notes is None:
        print(f"CHANGELOG.md has no release notes for {argv[0]}", file=sys.stderr)
        return 1
    print(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
