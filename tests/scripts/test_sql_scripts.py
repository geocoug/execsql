"""Run standalone .sql test scripts that self-verify via ASSERT.

Each ``.sql`` file in ``fixtures/`` is executed against a fresh SQLite
database.  Scripts use ``-- !x! ASSERT ...`` metacommands internally, so
a non-zero exit code means at least one assertion failed.

Two scripts have dedicated handlers below and are excluded from the
generic glob:

* ``audit_smoke.sql`` — parametrized across four kill-switch variants
  (baseline / ``--no-rm-file`` / ``--no-system-cmd`` / ``--no-serve``)
  to confirm both the success path and the rejection path of each flag.
* ``audit_lint_bad.sql`` — intentionally broken; exercised via
  ``--lint`` and asserted to emit at least two diagnostics.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_FIXTURES = Path(__file__).parent / "fixtures"
_AUDIT_SMOKE = _FIXTURES / "audit_smoke.sql"
_AUDIT_LINT_BAD = _FIXTURES / "audit_lint_bad.sql"
_DEDICATED = {_AUDIT_SMOKE.name, _AUDIT_LINT_BAD.name}
_SQL_SCRIPTS = sorted(s for s in _FIXTURES.glob("*.sql") if s.name not in _DEDICATED)


def _write_conf(tmp_path: Path, db_filename: str = "test.db") -> Path:
    """Write a minimal ``execsql.conf`` for SQLite into *tmp_path*."""
    conf = tmp_path / "execsql.conf"
    conf.write_text(
        textwrap.dedent(f"""\
            [connect]
            db_type = l
            db_file = {db_filename}
            new_db = yes
            password_prompt = no

            [encoding]
            script = utf-8
            output = utf-8
            import = utf-8
        """),
    )
    return conf


@pytest.mark.parametrize(
    "sql_script",
    _SQL_SCRIPTS,
    ids=[s.stem for s in _SQL_SCRIPTS],
)
def test_sql_script(tmp_path: Path, sql_script: Path) -> None:
    """Execute a self-verifying SQL script and assert exit-code 0."""
    _write_conf(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "execsql",
            str(sql_script),
            str(tmp_path / "test.db"),
            "-t",
            "l",
            "-n",
        ],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"Script {sql_script.name} failed (rc={result.returncode}).\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# audit_smoke.sql — exercise every kill-switch variant in one parametrization
# ---------------------------------------------------------------------------

# (variant_name, extra CLI flags for that variant)
_AUDIT_VARIANTS = [
    ("baseline", []),
    ("no-rm-file", ["--no-rm-file"]),
    ("no-system-cmd", ["--no-system-cmd"]),
    ("no-serve", ["--no-serve"]),
]


@pytest.mark.parametrize(
    "variant,extra_flags",
    _AUDIT_VARIANTS,
    ids=[v[0] for v in _AUDIT_VARIANTS],
)
def test_audit_smoke(tmp_path: Path, variant: str, extra_flags: list[str]) -> None:
    """Run audit_smoke.sql once per kill-switch variant.

    Each variant pairs a ``--no-*`` CLI flag with a matching ``-a`` so the
    script's Phase 7 can ASSERT both the success and rejection paths.
    The output directory is tmp_path so the test is hermetic.
    """
    _write_conf(tmp_path)
    outdir = tmp_path / "out"
    outdir.mkdir()
    cmd = [
        sys.executable,
        "-m",
        "execsql",
        *extra_flags,
        "--output-dir",
        str(outdir),
        "-t",
        "l",
        "-n",
        str(_AUDIT_SMOKE),
        str(tmp_path / "test.db"),
        "-a",
        variant,
        "-a",
        str(outdir),
    ]
    result = subprocess.run(
        cmd,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"audit_smoke variant={variant} failed (rc={result.returncode}).\n"
        f"CMD: {' '.join(cmd)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "ALL ASSERTIONS PASSED" in result.stdout, (
        f"audit_smoke variant={variant} missing success banner.\nSTDOUT:\n{result.stdout}"
    )


# ---------------------------------------------------------------------------
# audit_lint_bad.sql — confirm --lint emits the planted diagnostics
# ---------------------------------------------------------------------------


def test_audit_lint_bad(tmp_path: Path) -> None:
    """``execsql --lint`` on the intentionally broken fixture should
    report both planted diagnostics: an undefined substitution variable
    and a missing INCLUDE target."""
    result = subprocess.run(
        [sys.executable, "-m", "execsql", "--lint", str(_AUDIT_LINT_BAD)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
    )
    combined = result.stdout + result.stderr
    assert "totally_made_up_var" in combined, f"lint missed the undefined-variable warning.\nOUT:\n{combined}"
    assert "this_file_does_not_exist_98765.sql" in combined, (
        f"lint missed the missing-INCLUDE warning.\nOUT:\n{combined}"
    )
