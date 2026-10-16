"""What a failed metacommand leaves for the script: $LAST_ERROR, $ERROR_MESSAGE, METACOMMAND_ERROR().

With METACOMMAND_ERROR_HALT OFF the script carries on and can read both
variables; with it ON, an ON ERROR_HALT handler can.  The flag clears on the
next metacommand that succeeds; the variables keep their values until the next
error.
"""

from __future__ import annotations

import subprocess
import sys

from execsql import run

_FAILING = '-- !x! IMPORT TO NEW nofile FROM "does_not_exist.csv"\n'
_FAILED_COMMAND = 'IMPORT TO NEW nofile FROM "does_not_exist.csv"'


def _run(tmp_path, monkeypatch, sql: str):
    monkeypatch.chdir(tmp_path)
    result = run(sql=sql, dsn=f"sqlite:///{tmp_path / 't.db'}", new_db=True)
    out = tmp_path / "out.txt"
    return result, out.read_text().splitlines() if out.exists() else []


def test_without_halting_the_script_can_read_the_error(tmp_path, monkeypatch):
    result, lines = _run(
        tmp_path,
        monkeypatch,
        "-- !x! METACOMMAND_ERROR_HALT OFF\n" + _FAILING + "-- !x! IF (METACOMMAND_ERROR())\n"
        "-- !x!   WRITE `last=[!!$LAST_ERROR!!]` TO out.txt\n"
        "-- !x!   WRITE `message=[!!$ERROR_MESSAGE!!]` TO out.txt\n"
        "-- !x! ENDIF\n",
    )
    assert lines[0] == f"last=[{_FAILED_COMMAND}]"
    assert "does_not_exist.csv does not exist" in "\n".join(lines[1:])
    # The failure is one of the run's errors, as a non-halting SQL error is.
    assert not result.success
    assert [e.sql for e in result.errors] == [_FAILED_COMMAND]


def test_the_flag_clears_on_success_and_the_variables_keep_their_values(tmp_path, monkeypatch):
    _, lines = _run(
        tmp_path,
        monkeypatch,
        "-- !x! METACOMMAND_ERROR_HALT OFF\n" + _FAILING + "-- !x! WRITE `next` TO out.txt\n"
        "-- !x! IF (NOT METACOMMAND_ERROR())\n"
        "-- !x!   WRITE `cleared; last=[!!$LAST_ERROR!!]` TO out.txt\n"
        "-- !x! ENDIF\n",
    )
    assert lines == ["next", f"cleared; last=[{_FAILED_COMMAND}]"]


def test_an_on_error_halt_handler_can_read_the_error(tmp_path, monkeypatch):
    result, lines = _run(
        tmp_path,
        monkeypatch,
        "-- !x! BEGIN SCRIPT on_err\n"
        "-- !x! WRITE `handler last=[!!$LAST_ERROR!!]` TO out.txt\n"
        "-- !x! END SCRIPT\n"
        "-- !x! ON ERROR_HALT EXECUTE SCRIPT on_err\n" + _FAILING + "-- !x! WRITE `not reached` TO out.txt\n",
    )
    assert lines == [f"handler last=[{_FAILED_COMMAND}]"]
    assert not result.success


def test_the_documented_on_error_halt_write_example(tmp_path, monkeypatch):
    _, lines = _run(
        tmp_path,
        monkeypatch,
        '-- !x! ON ERROR_HALT WRITE "Error in line: !{$LAST_ERROR}!" TO out.txt\n' + _FAILING,
    )
    assert lines == [f"Error in line: {_FAILED_COMMAND}"]


def _cli(tmp_path, script: str) -> subprocess.CompletedProcess:
    (tmp_path / "s.sql").write_text(script)
    return subprocess.run(
        [sys.executable, "-m", "execsql", "run", "-tl", "-n", "s.sql", "t.db"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_the_cli_logs_a_non_halting_error_and_exits_zero(tmp_path):
    proc = _cli(tmp_path, "-- !x! METACOMMAND_ERROR_HALT OFF\n" + _FAILING)
    assert proc.returncode == 0, proc.stderr
    assert "Metacommand error:" in (tmp_path / "execsql.log").read_text()


def test_the_cli_still_halts_with_status_1(tmp_path):
    proc = _cli(tmp_path, _FAILING + "-- !x! WRITE `not reached`\n")
    assert proc.returncode == 1
    assert "not reached" not in proc.stdout
