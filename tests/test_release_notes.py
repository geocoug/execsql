"""``scripts/release_notes.py``: the text of each GitHub Release.

The tag build runs it before the PyPI upload and stops the release when
the script is missing or finds no notes for the tag.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "release_notes.py"

_spec = importlib.util.spec_from_file_location("release_notes", SCRIPT)
assert _spec is not None and _spec.loader is not None
release_notes_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_notes_module)
release_notes = release_notes_module.release_notes

SAMPLE = """\
# Changelog

## [Unreleased]

______________________________________________________________________

## [1.2.0] - 2026-01-02

### Added

- **`NEW`** metacommand.

______________________________________________________________________

## [1.1.0] - 2026-01-01

### Fixed

- **`OLD`** works.
"""


def _newest_release() -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(r"^## \[(\d[^\]]*)\]", text, re.MULTILINE)
    assert m, "CHANGELOG.md has no release section"
    return m.group(1)


def test_the_newest_release_has_release_notes():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), f"v{_newest_release()}"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("### ")


def test_a_section_ends_at_the_separator():
    assert release_notes("1.2.0", SAMPLE) == "### Added\n\n- **`NEW`** metacommand."
    assert release_notes("v1.1.0", SAMPLE) == "### Fixed\n\n- **`OLD`** works."


def test_a_missing_or_empty_section_has_no_notes():
    assert release_notes("1.3.0", SAMPLE) is None
    assert release_notes("Unreleased", SAMPLE) is None
    assert release_notes("1.2", SAMPLE) is None
