"""Go to definition, find references, the outline and INCLUDE links."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pygls")

from lsprotocol import types  # noqa: E402

from execsql.lsp.document import index_script  # noqa: E402
from execsql.lsp.navigation import definition, document_links, document_symbols, references  # noqa: E402

SCRIPT = """\
-- !x! SUB report_dir /tmp
-- !x! BEGIN SCRIPT load(table_name)
SELECT * FROM !!#table_name!!;
-- !x! END SCRIPT
-- !x! IF(hasrows(t))
-- !x! EXECUTE SCRIPT load WITH ARGUMENTS (table_name=t)
-- !x! ENDIF
-- !x! EXPORT t TO !!report_dir!!/a.csv AS CSV
-- !x! WRITE "!!report_dir!!"
"""
URI = "file:///work/main.sql"


def _cursor(needle: str, offset: int = 1) -> tuple[int, int]:
    for row, line in enumerate(SCRIPT.splitlines()):
        if needle in line:
            return row, line.index(needle) + offset
    raise AssertionError(needle)


def test_a_variable_goes_to_its_sub():
    found = definition(index_script(SCRIPT, None), URI, *_cursor("!!report_dir!!/", 3))
    assert [(d.range.start.line, d.range.start.character) for d in found] == [(0, 11)]
    assert found[0].uri == URI


def test_a_parameter_goes_to_its_script():
    found = definition(index_script(SCRIPT, None), URI, *_cursor("!!#table_name", 3))
    assert [d.range.start.line for d in found] == [1]


def test_execute_script_goes_to_begin_script():
    found = definition(index_script(SCRIPT, None), URI, *_cursor("SCRIPT load WITH", 8))
    assert [d.range.start.line for d in found] == [1]


def test_include_goes_to_the_file_and_a_variable_into_it(tmp_path):
    (tmp_path / "setup.sql").write_text("SELECT 1;\n-- !x! SUB region west\n")
    main = tmp_path / "main.sql"
    text = "-- !x! INCLUDE setup.sql\nSELECT '!!region!!';\n"
    index = index_script(text, str(main))
    to_file = definition(index, main.as_uri(), 0, 17)
    assert to_file[0].uri == (tmp_path / "setup.sql").resolve().as_uri()
    to_var = definition(index, main.as_uri(), 1, 12)
    assert to_var[0].uri.endswith("/setup.sql") and to_var[0].range.start.line == 1
    assert [Path(link.target).name for link in document_links(index)] == ["setup.sql"]


def test_references_find_every_use_and_the_definition():
    found = references(index_script(SCRIPT, None), URI, *_cursor("!!report_dir!!/", 3))
    assert sorted(d.range.start.line for d in found) == [0, 7, 8]
    without = references(index_script(SCRIPT, None), URI, *_cursor("!!report_dir!!/", 3), include_declaration=False)
    assert sorted(d.range.start.line for d in without) == [7, 8]


def test_the_outline_nests_blocks():
    symbols = document_symbols(index_script(SCRIPT, None), SCRIPT)
    names = [(s.name, s.kind) for s in symbols]
    assert ("report_dir", types.SymbolKind.Variable) in names
    assert ("SCRIPT load(table_name)", types.SymbolKind.Function) in names
    if_block = next(s for s in symbols if s.name.startswith("IF"))
    assert if_block.name == "IF (hasrows(t))"
    assert (if_block.range.start.line, if_block.range.end.line) == (4, 6)


def test_nothing_where_there_is_nothing():
    assert definition(index_script(SCRIPT, None), URI, 4, 2) == []
    assert references(index_script(SCRIPT, None), URI, 4, 2) == []
