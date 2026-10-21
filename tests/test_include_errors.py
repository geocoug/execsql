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


# INCLUDE and EXECUTE SCRIPT run the same way wherever they are written.


def test_an_include_in_an_inline_if_runs_the_file(tmp_path):
    out = tmp_path / "out.txt"
    (tmp_path / "part.sql").write_text(f'-- !x! WRITE "in part" TO {out}\n')
    result = _run(tmp_path, f"-- !x! IF (TRUE) {{ INCLUDE {tmp_path / 'part.sql'} }}\n")
    assert result.success, result.errors
    assert out.read_text().splitlines() == ["in part"]


def test_an_execute_script_in_an_inline_if_runs_the_script(tmp_path):
    out = tmp_path / "out.txt"
    result = _run(
        tmp_path,
        f'-- !x! BEGIN SCRIPT s\n-- !x! WRITE "in s" TO {out}\n-- !x! END SCRIPT\n'
        "-- !x! IF (TRUE) { EXECUTE SCRIPT s }\n",
    )
    assert result.success, result.errors
    assert out.read_text().splitlines() == ["in s"]


def test_an_include_added_with_extend_script_runs_the_file(tmp_path):
    out = tmp_path / "out.txt"
    (tmp_path / "part.sql").write_text(f'-- !x! WRITE "in part" TO {out}\n')
    result = _run(
        tmp_path,
        "-- !x! BEGIN SCRIPT s\n-- !x! END SCRIPT\n"
        f"-- !x! EXTEND SCRIPT s WITH METACOMMAND INCLUDE {tmp_path / 'part.sql'}\n"
        "-- !x! EXECUTE SCRIPT s\n",
    )
    assert result.success, result.errors
    assert out.read_text().splitlines() == ["in part"]


def test_an_include_a_variable_supplies_says_it_cannot_run(tmp_path):
    """-- !x! !!cmd!! goes to the dispatch table, which cannot run INCLUDE; the message says so."""
    result = _run(tmp_path, f"-- !x! SUB cmd INCLUDE {tmp_path / 'part.sql'}\n-- !x! !!cmd!!\n")
    assert not result.success
    assert "An INCLUDE that a substitution variable supplies cannot run" in result.errors[0].message


def test_an_execute_script_a_variable_supplies_says_it_cannot_run(tmp_path):
    sql = (
        '-- !x! BEGIN SCRIPT s\n-- !x! WRITE "in s"\n-- !x! END SCRIPT\n'
        "-- !x! SUB cmd EXECUTE SCRIPT s\n-- !x! !!cmd!!\n"
    )
    result = _run(tmp_path, sql)
    assert not result.success
    assert "An EXECUTE SCRIPT that a substitution variable supplies cannot run" in result.errors[0].message


def test_an_inline_if_a_variable_supplies_does_not_run(tmp_path):
    """Upstream ran it; execsql2 does not (#113)."""
    out = tmp_path / "out.txt"
    result = _run(tmp_path, f'-- !x! SUB cmd IF (TRUE) {{ WRITE "ran" TO {out} }}\n-- !x! !!cmd!!\n')
    assert not result.success
    assert "Line 2" in result.errors[0].message
    assert not out.exists()


def test_a_directive_a_variable_supplies_is_a_metacommand_error_with_halting_off(tmp_path):
    out = tmp_path / "out.txt"
    sql = (
        "-- !x! METACOMMAND_ERROR_HALT OFF\n"
        f'-- !x! SUB cmd IF (TRUE) {{ WRITE "ran" TO {out} }}\n'
        "-- !x! !!cmd!!\n"
        f'-- !x! IF (METACOMMAND_ERROR()) {{ WRITE "refused" TO {out} }}\n'
    )
    _run(tmp_path, sql)
    assert out.read_text() == "refused\n"


# EXECUTE SCRIPT's own errors are metacommand errors.


def test_a_missing_script_argument_is_a_metacommand_error_with_halting_off(tmp_path):
    out = tmp_path / "out.txt"
    result = _run(
        tmp_path,
        f'-- !x! BEGIN SCRIPT s (a)\n-- !x! WRITE "ran s" TO {out}\n-- !x! END SCRIPT\n'
        "-- !x! METACOMMAND_ERROR_HALT OFF\n"
        "-- !x! EXECUTE SCRIPT s\n"
        f'-- !x! IF (METACOMMAND_ERROR()) {{ WRITE "error: !!$LAST_ERROR!!" TO {out} }}\n'
        f'-- !x! WRITE "carried on" TO {out}\n',
    )
    assert len(result.errors) == 1  # recorded, and the run carried on
    assert out.read_text().splitlines() == ["error: EXECUTE SCRIPT s", "carried on"]


def test_a_missing_script_argument_halts_by_default(tmp_path):
    result = _run(
        tmp_path,
        '-- !x! BEGIN SCRIPT s (a)\n-- !x! WRITE "x"\n-- !x! END SCRIPT\n-- !x! EXECUTE SCRIPT s\n',
    )
    assert not result.success
    message = result.errors[0].message
    assert "Missing required parameter(s) (a) in call to s." in message
    assert "Metacommand: EXECUTE SCRIPT s" in message


def test_last_error_holds_the_include_as_it_ran(tmp_path):
    """Variables in the failed INCLUDE are substituted once, so $LAST_ERROR is the text that ran."""
    out = tmp_path / "out.txt"
    _run(
        tmp_path,
        "-- !x! METACOMMAND_ERROR_HALT OFF\n"
        f"-- !x! SUB dir {tmp_path}\n"
        "-- !x! INCLUDE !!dir!!/missing_!!$COUNTER_1!!.sql\n"
        f'-- !x! WRITE "!!$LAST_ERROR!!" TO {out}\n',
    )
    assert out.read_text().splitlines() == [f"INCLUDE {tmp_path}/missing_1.sql"]


# A condition that cannot be evaluated stops the run, reported on its own line.


def test_a_bad_if_condition_names_the_if(tmp_path):
    result = _run(tmp_path, '-- !x! IF (NO_SUCH_FN(x)) { WRITE "a" }\n')
    assert not result.success
    assert 'Metacommand: IF (NO_SUCH_FN(x)) { WRITE "a" }' in result.errors[0].message


def test_a_bad_elseif_condition_names_the_elseif_and_its_line(tmp_path):
    result = _run(
        tmp_path,
        '-- !x! IF (FALSE)\n-- !x! WRITE "a"\n-- !x! ELSEIF (NO_SUCH_FN(x))\n-- !x! WRITE "b"\n-- !x! ENDIF\n',
    )
    assert not result.success
    message = result.errors[0].message
    assert "Line 3 of script" in message
    assert "Metacommand: ELSEIF (NO_SUCH_FN(x))" in message


def test_a_bad_if_condition_stops_the_run_with_halting_off(tmp_path):
    out = tmp_path / "out.txt"
    result = _run(
        tmp_path,
        "-- !x! METACOMMAND_ERROR_HALT OFF\n"
        f'-- !x! IF (NO_SUCH_FN(x))\n-- !x! WRITE "if" TO {out}\n-- !x! ELSE\n-- !x! WRITE "else" TO {out}\n-- !x! ENDIF\n'
        f'-- !x! WRITE "carried on" TO {out}\n',
    )
    assert not result.success
    assert "Metacommand: IF (NO_SUCH_FN(x))" in result.errors[0].message
    assert not out.exists()


def test_a_bad_loop_condition_names_the_loop_when_evaluated_after_its_body(tmp_path):
    """LOOP UNTIL evaluates its condition after the body: the report names the LOOP, not the body's last line."""
    out = tmp_path / "out.txt"
    result = _run(
        tmp_path,
        f'-- !x! LOOP UNTIL (NO_SUCH_FN(x))\n-- !x! WRITE "looped" TO {out}\n-- !x! END LOOP\n',
    )
    assert not result.success
    message = result.errors[0].message
    assert "Line 1 of script" in message
    assert "Metacommand: LOOP UNTIL (NO_SUCH_FN(x))" in message
    assert out.read_text().splitlines() == ["looped"]


# include_root is a security boundary, not a script error.


def test_an_include_outside_include_root_halts_even_with_halting_off(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.sql"
    outside.write_text('-- !x! WRITE "outside"\n')
    conf = tmp_path / "execsql.conf"
    conf.write_text(f"[config]\ninclude_root = {root}\n")
    out = tmp_path / "out.txt"
    result = run(
        sql=f'-- !x! METACOMMAND_ERROR_HALT OFF\n-- !x! INCLUDE {outside}\n-- !x! WRITE "carried on" TO {out}\n',
        dsn=f"sqlite:///{tmp_path / 't.db'}",
        new_db=True,
        config_file=conf,
    )
    assert not result.success
    assert not out.exists()


# Only the file, script name and arguments are substituted; the metacommand is not parsed again.


def test_a_script_argument_with_a_line_break_is_passed_whole(tmp_path):
    out = tmp_path / "out.txt"
    result = _run(
        tmp_path,
        f'-- !x! BEGIN SCRIPT show (msg)\n-- !x! WRITE "!!#msg!!" TO {out}\n-- !x! END SCRIPT\n'
        "-- !x! METACOMMAND_ERROR_HALT OFF\n"
        f"-- !x! INCLUDE {tmp_path / 'missing.sql'}\n"
        '-- !x! EXECUTE SCRIPT show WITH ARGS (msg="!!$ERROR_MESSAGE!!")\n',
    )
    assert len(result.errors) == 1  # the INCLUDE; the EXECUTE SCRIPT ran
    assert "does not exist" in out.read_text()
    assert len(out.read_text().splitlines()) > 1


def test_include_if_exists_of_an_empty_variable_skips(tmp_path):
    out = tmp_path / "out.txt"
    result = _run(tmp_path, f'-- !x! SUB_EMPTY f\n-- !x! INCLUDE IF EXISTS !!f!!\n-- !x! WRITE "carried on" TO {out}\n')
    assert result.success, result.errors
    assert out.read_text().splitlines() == ["carried on"]


def test_write_script_writes_an_added_execute_script_as_written(tmp_path):
    out = tmp_path / "s.sql"
    _run(
        tmp_path,
        "-- !x! BEGIN SCRIPT inner\n-- !x! END SCRIPT\n-- !x! BEGIN SCRIPT outer\n-- !x! END SCRIPT\n"
        "-- !x! EXTEND SCRIPT outer WITH METACOMMAND EXECUTE SCRIPT inner UNTIL (1=1)\n"
        f"-- !x! WRITE SCRIPT outer TO {out}\n",
    )
    assert "-- !x! EXECUTE SCRIPT inner UNTIL (1=1)" in out.read_text().splitlines()


def test_on_error_halt_script_arguments_are_substituted_when_the_halt_fires(tmp_path):
    out = tmp_path / "out.txt"
    _run(
        tmp_path,
        # The cleanup script's own error changes $LAST_ERROR before it reads #msg.
        "-- !x! BEGIN SCRIPT cleanup (msg)\n-- !x! ERROR_HALT OFF\nselect * from other_table;\n"
        f'-- !x! WRITE "!!#msg!!" TO {out}\n-- !x! END SCRIPT\n'
        "-- !x! ON ERROR_HALT EXECUTE SCRIPT cleanup WITH ARGS (msg=!{$LAST_ERROR}!)\n"
        "select * from no_such_table;\n",
    )
    assert out.read_text().splitlines() == ["select * from no_such_table;"]


def test_an_inline_if_added_with_extend_script_runs(tmp_path):
    out = tmp_path / "out.txt"
    (tmp_path / "part.sql").write_text(f'-- !x! WRITE "in part" TO {out}\n')
    result = _run(
        tmp_path,
        "-- !x! BEGIN SCRIPT s\n-- !x! END SCRIPT\n"
        f"-- !x! EXTEND SCRIPT s WITH METACOMMAND IF (TRUE) {{ INCLUDE {tmp_path / 'part.sql'} }}\n"
        "-- !x! EXECUTE SCRIPT s\n",
    )
    assert result.success, result.errors
    assert out.read_text().splitlines() == ["in part"]


def test_a_bad_andif_condition_names_the_andif_and_its_line(tmp_path):
    result = _run(tmp_path, '-- !x! IF (TRUE)\n-- !x! ANDIF (NO_SUCH_FN(x))\n-- !x! WRITE "a"\n-- !x! ENDIF\n')
    assert not result.success
    message = result.errors[0].message
    assert "Line 2 of script" in message
    assert "Metacommand: ANDIF (NO_SUCH_FN(x))" in message


def test_a_missing_script_is_named_as_written(tmp_path):
    result = _run(tmp_path, "-- !x! EXECUTE SCRIPT MyReport\n")
    assert "There is no SCRIPT named MyReport." in result.errors[0].message


def test_an_include_outside_include_root_sets_last_error_for_on_error_halt(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.sql"
    outside.write_text('-- !x! WRITE "outside"\n')
    conf = tmp_path / "execsql.conf"
    conf.write_text(f"[config]\ninclude_root = {root}\n")
    out = tmp_path / "out.txt"
    run(
        sql=f'-- !x! ON ERROR_HALT WRITE "halted at: !{{$LAST_ERROR}}!" TO {out}\n-- !x! INCLUDE {outside}\n',
        dsn=f"sqlite:///{tmp_path / 't.db'}",
        new_db=True,
        config_file=conf,
    )
    assert out.read_text().splitlines() == [f"halted at: INCLUDE {outside}"]


def test_a_database_error_in_a_condition_still_stops_the_run(tmp_path):
    """HASROWS of a missing table is an SQL error, not a condition that cannot be evaluated."""
    out = tmp_path / "out.txt"
    result = _run(
        tmp_path,
        "-- !x! METACOMMAND_ERROR_HALT OFF\n"
        f'-- !x! IF (HASROWS(no_such_table)) {{ WRITE "if" TO {out} }}\n'
        f'-- !x! WRITE "carried on" TO {out}\n',
    )
    assert not result.success
    assert "no such table" in result.errors[0].message
    assert not out.exists()


def test_the_library_reports_the_line_of_a_bad_andif(tmp_path):
    """execsql.run() gives the line the report names, not the IF's."""
    result = _run(tmp_path, '-- !x! IF (TRUE)\n-- !x! WRITE "a"\n-- !x! ANDIF (NO_SUCH_FN(x))\n-- !x! ENDIF\n')
    assert result.errors[0].line == 3
    assert "Line 3 of script" in result.errors[0].message
