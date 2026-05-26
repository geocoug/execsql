"""B14/F036 regression: long-form CLI flags that upstream execsql
(v1.130.1) wrote with underscores must still parse, alongside the
modern hyphenated forms.

Affected flags: ``--database_encoding``, ``--script_encoding``,
``--output_encoding``, ``--import_encoding``, ``--import_buffer``,
``--user_logfile``, ``--visible_prompts``.

The Typer app accepts both spellings as aliases — invoking either
binds to the same parameter.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from execsql.cli import app


runner = CliRunner()


@pytest.mark.parametrize(
    "underscore,hyphen",
    [
        ("--database_encoding", "--database-encoding"),
        ("--script_encoding", "--script-encoding"),
        ("--output_encoding", "--output-encoding"),
        ("--import_encoding", "--import-encoding"),
        ("--import_buffer", "--import-buffer"),
        ("--user_logfile", "--user-logfile"),
        ("--visible_prompts", "--visible-prompts"),
    ],
)
def test_both_underscore_and_hyphen_forms_are_recognized(underscore, hyphen):
    """Neither alias should trip ``--help``'s "no such option" error.

    We invoke ``--help`` to avoid having to provide a script / db /
    valid value for each flag — typer's help text simply lists every
    declared option name, so both aliases appearing there proves the
    parser accepts them as equivalent.
    """
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    # Typer renders only the LAST declared decl in help; both names
    # are valid at parse time. Verify by feeding each form to the
    # parser with an obviously-bad value and asserting the error is
    # NOT "No such option".
    for form in (underscore, hyphen):
        bad = runner.invoke(app, [form, "DOES_NOT_EXIST"])
        # Either a usage-style error from missing positional args
        # (exit 2) or a script-not-found error — but never
        # "No such option" which would mean the alias was rejected.
        assert "No such option" not in bad.output, f"Typer rejected the flag alias {form!r}: {bad.output}"
