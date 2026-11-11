"""Dynamic block boundaries are refused without mutating a named script (#119)."""

import pytest

from execsql import run


BLOCKS = [
    "IF (TRUE)",
    "ELSEIF (TRUE)",
    "ANDIF (TRUE)",
    "ORIF (TRUE)",
    "ELSE",
    "ENDIF",
    "LOOP WHILE (TRUE)",
    "LOOP UNTIL (TRUE)",
    "END LOOP",
    "ENDLOOP",
    "BEGIN BATCH",
    "END BATCH",
    "BEGIN SCRIPT nested",
    "CREATE SCRIPT nested",
    "END SCRIPT",
    "BEGIN SQL",
    "END SQL",
    "IF (TRUE) { BEGIN BATCH }",
]


@pytest.mark.parametrize("command", BLOCKS)
@pytest.mark.parametrize("halt", [True, False])
def test_extend_rejects_block_boundaries_before_the_script_runs(command, halt):
    result = run(
        sql=(
            "-- !x! BEGIN SCRIPT s\n-- !x! SUB ran yes\n-- !x! END SCRIPT\n"
            f"-- !x! METACOMMAND_ERROR_HALT {'ON' if halt else 'OFF'}\n"
            f"-- !x! EXTEND SCRIPT s WITH METACOMMAND {command}\n"
            "-- !x! IF (METACOMMAND_ERROR()) { SUB refused yes }\n"
            "-- !x! EXECUTE SCRIPT s\n"
        ),
        dsn="sqlite:///:memory:",
    )
    assert not result.success
    assert len(result.errors) == 1
    assert "Line 5" in result.errors[0].message
    assert "write the complete block directly" in result.errors[0].message
    assert "WITH SCRIPT" in result.errors[0].message
    assert ("ran" in result.variables) is not halt
    assert ("refused" in result.variables) is not halt


@pytest.mark.parametrize("command", BLOCKS)
@pytest.mark.parametrize("halt", [True, False])
def test_variable_blocks_follow_metacommand_error_halt(command, halt):
    result = run(
        sql=(
            f"-- !x! METACOMMAND_ERROR_HALT {'ON' if halt else 'OFF'}\n"
            f"-- !x! SUB cmd {command}\n-- !x! !!cmd!!\n"
            "-- !x! IF (METACOMMAND_ERROR()) { SUB refused yes }\n"
        ),
        dsn="sqlite:///:memory:",
    )
    assert not result.success
    assert len(result.errors) == 1
    assert "Line 3" in result.errors[0].message
    assert "write the complete block directly" in result.errors[0].message
    assert ("refused" in result.variables) is not halt


def test_extend_with_script_appends_a_complete_block():
    result = run(
        sql=(
            "-- !x! BEGIN SCRIPT target\n-- !x! END SCRIPT\n"
            "-- !x! BEGIN SCRIPT source\n-- !x! IF (TRUE)\n"
            "-- !x! LOOP WHILE (TRUE)\n-- !x! BEGIN BATCH\n"
            "-- !x! SUB ran yes\n-- !x! END BATCH\n-- !x! BREAK\n"
            "-- !x! END LOOP\n-- !x! ENDIF\n-- !x! END SCRIPT\n"
            "-- !x! EXTEND SCRIPT target WITH SCRIPT source\n-- !x! EXECUTE SCRIPT target\n"
        ),
        dsn="sqlite:///:memory:",
    )
    assert result.success, result.errors
    assert result.variables["ran"] == "yes"
