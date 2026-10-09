"""Quick fixes for lint findings, offered only when they clear the finding."""

from __future__ import annotations

import pytest

pytest.importorskip("pygls")

from execsql.lsp.code_actions import code_actions  # noqa: E402
from execsql.lsp.diagnostics import diagnostics  # noqa: E402
from execsql.lsp.document import index_script  # noqa: E402

URI = "file:///work/main.sql"


def _fixes(source: str) -> list[tuple[str, str, list[tuple[int, int, str]]]]:
    found = diagnostics(source, None, (), ())
    actions = code_actions(index_script(source, None), URI, source, found)
    return [
        (
            a.diagnostics[0].code,
            a.title,
            [(e.range.start.line, e.range.start.character, e.new_text) for e in a.edit.changes[URI]],
        )
        for a in actions
    ]


def _apply(source: str, edits: list[tuple[int, int, str]]) -> str:
    lines = source.splitlines()
    for line, char, text in sorted(edits, reverse=True):
        lines[line] = lines[line][:char] + text + lines[line][char:]
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize(
    ("source", "title"),
    [
        ("-- !x! EXPROT orders TO a.csv AS CSV\n", "Change EXPROT to EXPORT"),
        ("-- !x! exprot orders TO a.csv AS CSV\n", "Change exprot to export"),
        ("-- !x! EXPORT orders TOO a.csv AS CSV\n", "Change TOO to TO"),
        ('-- !x! PRONPT MESSAGE "hi" DISPLAY t\n', "Change PRONPT to PROMPT"),
    ],
)
def test_a_misspelled_metacommand_word(source, title):
    assert [(code, t) for code, t, _ in _fixes(source)] == [("P003", title)]


def test_the_metacommand_fix_clears_the_finding():
    source = "-- !x! EXPROT orders TO a.csv AS CSV\n"
    ((_, _, edits),) = _fixes(source)
    fixed = source.replace("EXPROT", edits[0][2])
    assert not diagnostics(fixed, None, (), ())


def test_no_fix_when_nothing_close_matches():
    assert _fixes("-- !x! FROBNICATE everything\n") == []


def test_a_misspelled_condition():
    source = "-- !x! IF(hasrowz(orders))\n-- !x! ENDIF\n"
    assert _fixes(source) == [("P004", "Change hasrowz to hasrows", [(0, 10, "hasrows")])]


def test_a_near_miss_variable():
    source = '-- !x! SUB report_dir /tmp\n-- !x! WRITE "!!report_dri!!"\n'
    assert _fixes(source) == [("V001", "Change !!report_dri!! to !!report_dir!!", [(1, 16, "report_dir")])]


def test_a_near_miss_system_variable():
    titles = [t for code, t, _ in _fixes('-- !x! WRITE "!!$CURRENT_DAT!!"\n') if code == "V001"]
    assert titles[0] == "Change !!$CURRENT_DAT!! to !!$CURRENT_DATE!!"


def test_a_split_dollar_quote_is_wrapped():
    source = (
        "create function f() returns void as $body$\n"
        "begin\n"
        "    delete from t;\n"
        "end;\n"
        "$body$ language plpgsql;\n"
        "select 1;\n"
    )
    ((code, title, edits),) = _fixes(source)
    assert (code, title) == ("P002", "Put the statement between BEGIN SQL and END SQL")
    assert edits == [(0, 0, "-- !x! BEGIN SQL\n"), (4, 24, "\n-- !x! END SQL")]
    fixed = _apply(source, edits)
    assert fixed.splitlines()[0] == "-- !x! BEGIN SQL"
    assert fixed.splitlines()[6] == "-- !x! END SQL"
    assert not diagnostics(fixed, None, (), ())


def test_other_findings_have_no_fix():
    assert _fixes("-- !x! SUB unused 1\n") == []
