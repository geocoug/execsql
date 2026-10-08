"""Completion offers readable syntax: metacommands, conditional tests, variables and export formats."""

from __future__ import annotations

import pytest

pytest.importorskip("pygls")

from lsprotocol import types  # noqa: E402

from execsql.lsp.completion import completions  # noqa: E402
from execsql.lsp.document import index_script  # noqa: E402


def _complete(text: str, path: str | None = None, snippets: bool = True):
    """Complete at the ``|`` in *text*."""
    row = next(n for n, line in enumerate(text.splitlines()) if "|" in line)
    line = text.splitlines()[row]
    col = line.index("|")
    source = text.replace("|", "", 1)
    return completions(index_script(source, path), source, row, col, snippets=snippets).items


def _new_text(items, label):
    return [i.text_edit.new_text for i in items if i.label == label]


class TestMetacommands:
    def test_every_syntax_line_is_offered_as_a_template(self):
        items = _complete("-- !x! exp|\n")
        assert "EXPORT ${1:table_or_view} TO ${2:filename} AS ${3:format}" in _new_text(items, "EXPORT")
        assert len(_new_text(items, "EXPORT")) == 2  # the AS <format> and WITH TEMPLATE forms
        assert _new_text(items, "EXPORT QUERY")[0].startswith("EXPORT QUERY <<${1:query}>>")

    def test_the_typed_word_is_replaced(self):
        item = next(i for i in _complete("  -- !x! exp|\n") if i.label == "EXPORT")
        assert item.text_edit.range.start == types.Position(line=0, character=9)
        assert item.text_edit.range.end == types.Position(line=0, character=12)
        assert item.insert_text_format == types.InsertTextFormat.Snippet

    def test_items_carry_summary_syntax_and_docs_link(self):
        item = next(i for i in _complete("-- !x! |\n") if i.label == "COPY")
        assert "Copies a table or view" in item.documentation.value
        assert "/reference/metacommands/#copy" in item.documentation.value

    def test_after_a_space_only_longer_keywords_continue(self):
        labels = {i.label for i in _complete("-- !x! EXPORT |\n")}
        assert labels == {"EXPORT QUERY"}

    def test_without_snippet_support_the_keyword_is_inserted(self):
        item = next(i for i in _complete("-- !x! su|\n", snippets=False) if i.label == "SUB")
        assert item.text_edit.new_text == "SUB"
        assert item.insert_text_format == types.InsertTextFormat.PlainText

    def test_nothing_on_a_sql_line(self):
        assert _complete("SELECT * FROM t WHERE |\n") == []


class TestConditions:
    @pytest.mark.parametrize(
        "line",
        [
            "-- !x! IF(has|",
            "-- !x! ELSEIF(has|",
            "-- !x! ASSERT has|",
            "-- !x! LOOP WHILE (has|",
            "-- !x! IF(sub_defined(x) AND has|",
        ],
    )
    def test_conditional_tests_inside_a_condition(self, line):
        assert _new_text(_complete(line + "\n"), "HASROWS") == ["HASROWS(${1:table_or_view})"]


class TestVariables:
    SCRIPT = "-- !x! SUB report_dir /tmp\n-- !x! BEGIN SCRIPT load(table_name)\n-- !x! END SCRIPT\n"

    def test_the_scripts_own_variables_with_where_they_are_defined(self):
        items = _complete(self.SCRIPT + '-- !x! WRITE "!!rep|"\n')
        item = next(i for i in items if i.label == "report_dir")
        assert item.detail == "defined at line 1"
        assert item.text_edit.new_text == "report_dir!!"

    def test_system_variables_and_parameters(self):
        items = _complete(self.SCRIPT + "SELECT '!!|';\n")
        labels = {i.label for i in items}
        assert {"$CURRENT_DATE", "#table_name", "report_dir"} <= labels
        assert _new_text(items, "$ARG_n") == ["\\$ARG_${1:1}!!"]

    def test_a_sigil_narrows_the_list(self):
        labels = {i.label for i in _complete(self.SCRIPT + "SELECT '!!$|';\n")}
        assert "report_dir" not in labels and "$CURRENT_DATE" in labels

    def test_the_closing_delimiter_is_not_doubled(self):
        items = _complete(self.SCRIPT + "SELECT '!!rep|!!';\n")
        assert _new_text(items, "report_dir") == ["report_dir"]

    @pytest.mark.parametrize(("opener", "closing"), [("!{", "}!"), ("!'!", "!'!"), ('!"!', '!"!')])
    def test_other_variable_forms_get_their_own_closing(self, opener, closing):
        items = _complete(self.SCRIPT + f"SELECT {opener}rep|;\n")
        assert _new_text(items, "report_dir") == ["report_dir" + closing]

    def test_variables_from_included_files(self, tmp_path):
        (tmp_path / "setup.sql").write_text("-- !x! SUB region west\n")
        main = tmp_path / "main.sql"
        items = _complete('-- !x! INCLUDE setup.sql\n-- !x! WRITE "!!reg|"\n', str(main))
        item = next(i for i in items if i.label == "region")
        assert "setup.sql" in item.detail


def test_export_formats_after_as():
    labels = {i.label for i in _complete("-- !x! EXPORT t TO out.json AS js|\n")}
    assert {"CSV", "JSON", "XLSX"} <= labels
