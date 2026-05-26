"""Regression tests for the bundled ``templates/*.sql`` files.

Covers audit findings F053 (unterminated string literals in script_template.sql),
F054 verified non-bug (case-insensitive CONFIG keyword matching), and F055
(unsafe ``'!!#var!!'`` substitution form in upsert/compare/glossary templates).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "templates"

# Templates the audit explicitly flagged in F055 — these must use the safe
# ``!'!#var!'!`` form, never the unsafe ``'!!#var!!'`` form.
UNSAFE_SUB_GUARDED = sorted(
    p.name
    for p in TEMPLATES_DIR.glob("*.sql")
    if p.name.startswith(("pg_", "md_", "ss_"))
    and any(p.name.endswith(suffix) for suffix in ("_upsert.sql", "_compare.sql", "_glossary.sql"))
)

# Every bundled .sql template must lint without a non-zero exit.
ALL_TEMPLATES = sorted(p.name for p in TEMPLATES_DIR.glob("*.sql"))


@pytest.mark.parametrize("template_name", ALL_TEMPLATES)
def test_template_lints_cleanly(template_name: str) -> None:
    """Every bundled .sql template must lint without a parser/syntax error."""
    template_path = TEMPLATES_DIR / template_name
    result = subprocess.run(
        [sys.executable, "-m", "execsql", "--lint", str(template_path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    # --lint returns 0 even when warnings exist; non-zero indicates a fatal
    # parse/syntax error (e.g. the F053 unterminated-string regression).
    assert result.returncode == 0, (
        f"--lint failed for {template_name} (exit {result.returncode}).\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.parametrize("template_name", UNSAFE_SUB_GUARDED)
def test_no_unsafe_substitution_form(template_name: str) -> None:
    """F055: upsert/compare/glossary templates must use ``!'!#var!'!`` not ``'!!#var!!'``."""
    text = (TEMPLATES_DIR / template_name).read_text()
    unsafe = re.findall(r"'!!#\w+!!'", text)
    assert not unsafe, (
        f"{template_name} contains unsafe substitution form {unsafe!r}; "
        f"use !'!#var!'! instead so single quotes in the substituted value are escaped."
    )


def test_script_template_no_unterminated_write_strings() -> None:
    """F053 regression: WRITE quoted-string clauses in script_template.sql must close their quotes."""
    text = (TEMPLATES_DIR / "script_template.sql").read_text()
    # Each ``-- !x! write "..." [tee] to !!file!!`` line must contain a balanced
    # pair of double quotes before the ``to`` clause.
    bad: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.lower().startswith('-- !x! write "'):
            continue
        # Strip the leading metacommand prefix, then count quotes before ' to '
        body = stripped[len("-- !x! write ") :]
        # Find the index of the unquoted ` to ` separator (case-insensitive)
        match = re.search(r"\s+to\s+", body, flags=re.IGNORECASE)
        if not match:
            continue
        quoted_part = body[: match.start()]
        if quoted_part.count('"') % 2 != 0:
            bad.append((lineno, line))
    assert not bad, f"Unterminated string literals in WRITE metacommands: {bad}"
