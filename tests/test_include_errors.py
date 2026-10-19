"""INCLUDE and EXECUTE SCRIPT that fail themselves are metacommand errors, as in upstream execsql."""

from __future__ import annotations

from execsql import run


def _run(tmp_path, sql):
    return run(sql=sql, dsn=f"sqlite:///{tmp_path / 't.db'}", new_db=True)


def test_a_missing_include_file_halts_by_default_and_names_the_metacommand(tmp_path):
    result = _run(tmp_path, f"-- !x! INCLUDE {tmp_path / 'missing.sql'}\n")
    assert not result.success
    message = result.errors[0].message
    assert "does not exist" in message
    assert f"Metacommand: INCLUDE {tmp_path / 'missing.sql'}" in message


def test_a_missing_include_file_is_a_metacommand_error_with_halting_off(tmp_path):
    out = tmp_path / "out.txt"
    result = _run(
        tmp_path,
        "-- !x! METACOMMAND_ERROR_HALT OFF\n"
        f"-- !x! INCLUDE {tmp_path / 'missing.sql'}\n"
        f'-- !x! IF (METACOMMAND_ERROR()) {{ WRITE "error: !!$LAST_ERROR!!" TO {out} }}\n'
        f'-- !x! WRITE "carried on" TO {out}\n',
    )
    assert result.variables["error_message"]
    assert out.read_text().splitlines() == [f"error: INCLUDE {tmp_path / 'missing.sql'}", "carried on"]


def test_a_missing_script_is_a_metacommand_error_with_halting_off(tmp_path):
    out = tmp_path / "out.txt"
    _run(
        tmp_path,
        "-- !x! METACOMMAND_ERROR_HALT OFF\n"
        "-- !x! EXECUTE SCRIPT no_such_script\n"
        f'-- !x! IF (METACOMMAND_ERROR()) {{ WRITE "error seen" TO {out} }}\n',
    )
    assert out.read_text().splitlines() == ["error seen"]


def test_an_error_inside_an_included_file_is_not_the_include_failing(tmp_path):
    """A failed SQL statement in the included file stops the run (ERROR_HALT), whatever METACOMMAND_ERROR_HALT says."""
    part = tmp_path / "part.sql"
    part.write_text("select * from no_such_table;\n")
    out = tmp_path / "out.txt"
    result = _run(
        tmp_path,
        f'-- !x! METACOMMAND_ERROR_HALT OFF\n-- !x! INCLUDE {part}\n-- !x! WRITE "after" TO {out}\n',
    )
    assert not result.success
    assert "no such table" in result.errors[0].message
    assert not out.exists()
