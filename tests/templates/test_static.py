"""What holds for every template without a database server: lint, INCLUDE, the config database.

These run on every OS in the normal test jobs; the behaviour tests beside
them need live servers.
"""

from __future__ import annotations

import re
import sqlite3
import subprocess
import sys

import pytest

from execsql import run

from .conftest import TEMPLATES

ALL = sorted(TEMPLATES.glob("*.sql"))
# Files that are libraries of scripts: INCLUDE defines them and runs nothing.
LIBRARIES = [p for p in ALL if p.stem.split("_", 1)[0] in ("pg", "md", "ss")]


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.name)
def test_lints_without_errors(path):
    """Warnings are expected (variables a host script defines); errors are not."""
    result = subprocess.run(
        [sys.executable, "-m", "execsql", "lint", str(path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("path", LIBRARIES, ids=lambda p: p.name)
def test_a_library_includes_without_running_anything(path, tmp_path):
    result = run(sql=f'-- !x! INCLUDE "{path.as_posix()}"\n', dsn=f"sqlite:///{tmp_path / 't.db'}", new_db=True)
    assert result.success, result.errors
    assert sqlite3.connect(tmp_path / "t.db").execute("select count(*) from sqlite_master").fetchone() == (0,)


def test_config_settings_db_is_what_make_config_db_builds(tmp_path):
    built = tmp_path / "config.sqlite"
    result = run(script=TEMPLATES / "make_config_db.sql", dsn=f"sqlite:///{built}", new_db=True)
    assert result.success, result.errors

    def specs(path):
        with sqlite3.connect(path) as conn:
            return conn.execute("select * from configspecs order by sub_var").fetchall()

    assert specs(TEMPLATES / "config_settings.sqlite") == specs(built)


@pytest.mark.parametrize("prefix", ["pg", "md", "ss"])
@pytest.mark.parametrize(
    ("family", "script", "optional", "doc"),
    [
        ("glossary", "ADD_GLOSSARY_ITEM", "def_url", "Add an object name and definition to the custom glossary."),
        ("compare", "COMPARE_COMMON", "exclude_cols", "Generate SQL to compare the attributes of base and staging"),
    ],
)
def test_scripts_document_themselves(prefix, family, script, optional, doc, tmp_path):
    """SHOW SCRIPTS (and the editor's hover) shows a script's notes and its optional parameters."""
    show = tmp_path / "show.sql"
    show.write_text(
        f'-- !x! INCLUDE "{(TEMPLATES / f"{prefix}_{family}.sql").as_posix()}"\n-- !x! SHOW SCRIPTS {script}\n',
    )
    out = subprocess.run(
        [sys.executable, "-m", "execsql", "run", str(show), str(tmp_path / "t.db"), "-t", "l", "-n"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert re.search(rf"{optional}\s+\(optional, default: \)", out)
    assert doc in out
