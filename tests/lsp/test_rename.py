"""Rename a user variable in the script and the files it includes, or refuse."""

from __future__ import annotations

import pytest

pytest.importorskip("pygls")

from lsprotocol import types  # noqa: E402

from execsql.lsp.document import index_script  # noqa: E402
from execsql.lsp.rename import RenameError, prepare_rename, rename  # noqa: E402

URI = "file:///work/main.sql"


def _apply(text: str, edits: list[types.TextEdit]) -> str:
    lines = text.splitlines(keepends=True)
    for edit in sorted(edits, key=lambda e: (e.range.start.line, e.range.start.character), reverse=True):
        row, line = edit.range.start.line, lines[edit.range.start.line]
        lines[row] = line[: edit.range.start.character] + edit.new_text + line[edit.range.end.character :]
    return "".join(lines)


def _rename(text: str, row: int, col: int, new: str) -> str:
    edit = rename(index_script(text, None), URI, row, col, new)
    assert edit is not None and edit.changes is not None
    return _apply(text, edit.changes[URI])


def test_every_use_and_the_definition_are_renamed():
    text = "-- !x! SUB region north\nSELECT '!!region!!', !'!region!'!, !{region}!;\n-- !x! WRITE !!REGION!!\n"
    assert _rename(text, 1, 10, "area") == (
        "-- !x! SUB area north\nSELECT '!!area!!', !'!area!'!, !{area}!;\n-- !x! WRITE !!area!!\n"
    )


def test_rename_from_the_definition():
    text = "-- !x! SUB region north\nSELECT '!!region!!';\n"
    assert _rename(text, 0, 12, "area") == "-- !x! SUB area north\nSELECT '!!area!!';\n"


def test_a_variable_nested_in_another_name_is_renamed():
    text = "-- !x! SUB grp east\n-- !x! SUB N_!!grp!!_X 1\nSELECT !!N_!!grp!!_X!!;\n"
    assert _rename(text, 0, 12, "g") == "-- !x! SUB g east\n-- !x! SUB N_!!g!!_X 1\nSELECT !!N_!!g!!_X!!;\n"


def test_a_local_variable_keeps_its_prefix():
    text = "-- !x! SUB ~tmp 1\nSELECT !!~tmp!!;\n"
    assert _rename(text, 1, 11, "scratch") == "-- !x! SUB ~scratch 1\nSELECT !!~scratch!!;\n"


def test_uses_in_an_included_file_are_renamed(tmp_path):
    (tmp_path / "setup.sql").write_text("-- !x! SUB region north\n", encoding="utf-8")
    main = tmp_path / "main.sql"
    text = "-- !x! INCLUDE setup.sql\nSELECT '!!region!!';\n"
    edit = rename(index_script(text, str(main)), main.as_uri(), 1, 11, "area")
    assert edit is not None and edit.changes is not None
    assert _apply(text, edit.changes[main.as_uri()]) == "-- !x! INCLUDE setup.sql\nSELECT '!!area!!';\n"
    setup = (tmp_path / "setup.sql").as_uri()
    assert _apply("-- !x! SUB region north\n", edit.changes[setup]) == "-- !x! SUB area north\n"


@pytest.mark.parametrize("name", ["$DATE_TAG", "&HOME", "@col", "#param"])
def test_system_environment_column_and_parameter_names_are_not_renamed(name):
    text = f"SELECT '!!{name}!!';\n"
    assert prepare_rename(index_script(text, None), 0, 11) is None
    assert rename(index_script(text, None), URI, 0, 11, "x") is None


def test_prepare_gives_the_bare_name():
    found = prepare_rename(index_script("SELECT '!!~tmp!!';\n", None), 0, 12)
    assert found == types.Range(start=types.Position(line=0, character=11), end=types.Position(line=0, character=14))


@pytest.mark.parametrize(
    ("new", "message"),
    [("a b", "not a variable name"), ("$x", "not a variable name"), ("other", "already defined")],
)
def test_a_rename_that_would_be_wrong_is_refused(new, message):
    text = "-- !x! SUB region north\n-- !x! SUB other 1\nSELECT '!!region!!', '!!other!!';\n"
    with pytest.raises(RenameError, match=message):
        rename(index_script(text, None), URI, 2, 11, new)


def test_a_name_used_as_local_and_global_is_refused():
    text = "-- !x! SUB x 1\n-- !x! SUB ~x 2\nSELECT !!x!!, !!~x!!;\n"
    with pytest.raises(RenameError, match="local"):
        rename(index_script(text, None), URI, 2, 9, "y")


def test_renaming_to_the_same_name_in_another_case_is_allowed():
    assert _rename("-- !x! SUB region n\nSELECT !!region!!;\n", 1, 10, "REGION") == (
        "-- !x! SUB REGION n\nSELECT !!REGION!!;\n"
    )
