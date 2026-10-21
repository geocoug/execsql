"""BREAK leaves the innermost LOOP, SCRIPT or included file (#115)."""

from __future__ import annotations

from execsql import run


def _run(tmp_path, sql):
    return run(sql=sql, dsn=f"sqlite:///{tmp_path / 't.db'}", new_db=True)


def _lines(tmp_path):
    return (tmp_path / "out.txt").read_text().splitlines()


def test_break_in_a_script_returns_from_it(tmp_path):
    out = tmp_path / "out.txt"
    sql = (
        "-- !x! BEGIN SCRIPT s\n"
        f'-- !x! WRITE "in s" TO {out}\n'
        "-- !x! BREAK\n"
        f'-- !x! WRITE "after break" TO {out}\n'
        "-- !x! END SCRIPT\n"
        "-- !x! EXECUTE SCRIPT s\n"
        f'-- !x! WRITE "after script" TO {out}\n'
    )
    assert _run(tmp_path, sql).success
    assert _lines(tmp_path) == ["in s", "after script"]


def test_break_in_an_included_file_inside_a_loop_leaves_only_the_file(tmp_path):
    out = tmp_path / "out.txt"
    part = tmp_path / "part.sql"
    part.write_text(f'-- !x! WRITE "in part" TO {out}\n-- !x! BREAK\n-- !x! WRITE "after break" TO {out}\n')
    sql = (
        "-- !x! SUB n 0\n"
        "-- !x! LOOP WHILE (IS_GT(2, !{n}!))\n"
        "-- !x! SUB_ADD n 1\n"
        f"-- !x! INCLUDE {part}\n"
        f'-- !x! WRITE "pass !!n!!" TO {out}\n'
        "-- !x! END LOOP\n"
    )
    assert _run(tmp_path, sql).success
    assert _lines(tmp_path) == ["in part", "pass 1", "in part", "pass 2"]


def test_break_in_a_loop_inside_a_script_leaves_the_loop_not_the_script(tmp_path):
    out = tmp_path / "out.txt"
    sql = (
        "-- !x! BEGIN SCRIPT s\n"
        "-- !x! LOOP WHILE (TRUE)\n"
        "-- !x! BREAK\n"
        "-- !x! END LOOP\n"
        f'-- !x! WRITE "after loop, in s" TO {out}\n'
        "-- !x! END SCRIPT\n"
        "-- !x! EXECUTE SCRIPT s\n"
    )
    assert _run(tmp_path, sql).success
    assert _lines(tmp_path) == ["after loop, in s"]


def test_break_at_the_top_level_halts_and_names_its_own_line(tmp_path):
    result = _run(tmp_path, '-- !x! WRITE "before"\n-- !x! BREAK\n-- !x! WRITE "after"\n')
    assert not result.success
    message = result.errors[0].message
    assert "BREAK has nothing to leave" in message
    assert "Line 2" in message
    assert "Metacommand: BREAK" in message


def test_break_at_the_top_level_is_a_metacommand_error_with_halting_off(tmp_path):
    out = tmp_path / "out.txt"
    sql = (
        "-- !x! METACOMMAND_ERROR_HALT OFF\n"
        "-- !x! BREAK\n"
        f'-- !x! IF (METACOMMAND_ERROR()) {{ WRITE "error seen" TO {out} }}\n'
        f'-- !x! WRITE "carried on" TO {out}\n'
    )
    _run(tmp_path, sql)
    assert _lines(tmp_path) == ["error seen", "carried on"]
