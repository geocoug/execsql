"""Run standalone .sql test scripts that self-verify via ASSERT.

Each ``.sql`` file in ``fixtures/`` is executed against a fresh SQLite
database.  Scripts use ``-- !x! ASSERT ...`` metacommands internally, so
a non-zero exit code means at least one assertion failed.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_FIXTURES = Path(__file__).parent / "fixtures"
_SQL_SCRIPTS = sorted(_FIXTURES.glob("*.sql"))


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
