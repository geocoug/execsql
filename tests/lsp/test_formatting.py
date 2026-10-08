"""Format Document: the same result as `execsql format`."""

from __future__ import annotations

import pytest

pytest.importorskip("pygls")
pytest.importorskip("sqlglot")

from execsql.format import format_file  # noqa: E402
from execsql.lsp.formatting import format_document  # noqa: E402

SCRIPT = "-- !x! if(hasrows(t))\nselect a,b from t where x=1;\n-- !x! endif\n"


def test_the_whole_document_is_replaced_with_execsql_format_output():
    (edit,) = format_document(SCRIPT)
    assert edit.new_text == format_file(SCRIPT)
    assert (edit.range.start.line, edit.range.start.character) == (0, 0)
    assert (edit.range.end.line, edit.range.end.character) == (3, 0)


def test_a_formatted_document_needs_no_edit():
    assert format_document(format_file(SCRIPT)) == []


def test_without_a_final_newline_the_edit_ends_on_the_last_line():
    (edit,) = format_document('select 1;\n-- !x! write "é😀"')
    assert (edit.range.end.line, edit.range.end.character) == (1, 18)


def test_format_options_apply():
    (edit,) = format_document(SCRIPT, indent=2, use_sql=False)
    assert edit.new_text == format_file(SCRIPT, indent=2, use_sql=False)
    assert "select a,b from t where x=1;" in edit.new_text
