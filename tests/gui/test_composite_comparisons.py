"""Composite comparisons must match named keys independently of column order."""

from __future__ import annotations

import asyncio
from itertools import permutations

import pytest

from execsql import run, state
from execsql.db.sqlite import SQLiteDatabase
from execsql.gui.base import compare_stats, compute_row_diffs
from execsql.metacommands import prompt

HEADERS1 = ["id", "grp", "value"]
ROWS1 = [(1, "A", "same"), (2, "B", "old"), (3, "C", "left")]
HEADERS2 = ["grp", "value", "id"]
ROWS2 = [("D", "right", 4), ("B", "new", 2), ("A", "same", 1)]
SUMMARY = "1 matching | 1 differing | 1 only in Table 1 | 1 only in Table 2"


def reordered(headers, source_headers, rows):
    return [tuple(row[source_headers.index(column)] for column in headers) for row in rows]


def test_all_column_permutations_preserve_composite_matches_and_changed_columns():
    for headers1 in permutations(HEADERS1):
        for headers2 in permutations(HEADERS2):
            for keys in (["id", "grp"], ["grp", "id"]):
                diff = compute_row_diffs(
                    list(headers1),
                    reordered(headers1, HEADERS1, ROWS1),
                    list(headers2),
                    reordered(headers2, HEADERS2, ROWS2),
                    keys,
                )
                assert diff is not None
                assert diff.table1_row_states == ["match", "changed", "only_t1"]
                assert diff.table2_row_states == ["only_t2", "changed", "match"]
                assert diff.table1_changed_cols == [set(), {"value"}, set()]
                assert diff.table2_changed_cols == [set(), {"value"}, set()]
                assert diff.summary == SUMMARY


@pytest.mark.parametrize("side", [1, 2])
@pytest.mark.parametrize("missing", ["id", "grp"])
@pytest.mark.parametrize("empty", [False, True])
def test_missing_part_of_composite_key_disables_comparison(side, missing, empty):
    h1 = [h for h in HEADERS1 if side != 1 or h != missing]
    h2 = [h for h in HEADERS2 if side != 2 or h != missing]
    r1 = [] if empty else reordered(h1, HEADERS1, ROWS1)
    r2 = [] if empty else reordered(h2, HEADERS2, ROWS2)
    assert compute_row_diffs(h1, r1, h2, r2, ["id", "grp"]) is None
    assert compare_stats(h1, r1, h2, r2, ["id", "grp"]) == ""


def test_reordered_composite_duplicates_still_keep_first_row():
    diff = compute_row_diffs(
        HEADERS1,
        [(1, "A", "same"), (1, "A", "ignored")],
        HEADERS2,
        [("A", "same", 1), ("A", "also ignored", 1)],
        ["id", "grp"],
    )
    assert diff is not None
    assert diff.table1_row_states == diff.table2_row_states == ["match", ""]
    assert diff.table1_changed_cols == diff.table2_changed_cols == [set(), set()]
    assert diff.summary == "1 matching"


def comparison_args():
    return {"headers1": HEADERS1, "rows1": ROWS1, "headers2": HEADERS2, "rows2": ROWS2, "keylist": ["id", "grp"]}


def test_real_compare_prompt_renders_correct_console_summary_and_markers(monkeypatch, capsys):
    from execsql.gui.console import ConsoleBackend

    class Manager:
        def put(self, spec):
            spec.return_queue.put(ConsoleBackend().dispatch(spec))

    monkeypatch.setattr(prompt, "enable_gui", lambda: setattr(state, "gui_manager_queue", Manager()))
    monkeypatch.setattr("builtins.input", lambda *args: "1")
    db = SQLiteDatabase(":memory:")
    try:
        db.conn.executescript(
            "create table first_table (id integer, grp text, value text);"
            "insert into first_table values (1,'A','same'),(2,'B','old'),(3,'C','left');"
            "create table second_table (grp text, value text, id integer);"
            "insert into second_table values ('D','right',4),('B','new',2),('A','same',1);",
        )
        result = run(
            sql='-- !x! PROMPT COMPARE first_table BESIDE second_table KEY(id, grp) MESSAGE "Compare"\n',
            connection=db,
        )
        assert result.success, result.errors
        rendered = capsys.readouterr().err
        assert SUMMARY in rendered
        assert "● old" in rendered and "● new" in rendered
        assert "● same" not in rendered
    finally:
        db.close()


@pytest.mark.parametrize("missing_key", [False, True])
def test_textual_reordered_keys_sync_selection_and_render_diffs(missing_key):
    pytest.importorskip("textual")
    from textual.coordinate import Coordinate
    from textual.widgets import DataTable

    from execsql.gui.tui import CompareScreen, _SingleDialogApp

    async def interact():
        args = comparison_args()
        if missing_key:
            args["keylist"] = ["id", "missing"]
        app = _SingleDialogApp(CompareScreen, args)
        async with app.run_test(size=(100, 40)) as pilot:
            screen = app.screen
            left = screen.query_one("#table1", DataTable)
            right = screen.query_one("#table2", DataTable)
            left.focus()
            await pilot.press("down", "up")
            await pilot.pause()
            assert left.cursor_row == 0
            assert right.cursor_row == (0 if missing_key else 2)
            assert await pilot.click("#btn_diff_toggle")
            await pilot.pause()
            if missing_key:
                assert screen._diff_result is None
                assert str(left.get_cell_at(Coordinate(1, 2))) == "old"
                assert str(right.get_cell_at(Coordinate(1, 1))) == "new"
            else:
                assert str(left.get_cell_at(Coordinate(1, 2))) == "● old"
                assert str(right.get_cell_at(Coordinate(1, 1))) == "● new"
                assert screen._diff_result.summary == SUMMARY
            assert str(left.get_cell_at(Coordinate(0, 2))) == "same"
            await pilot.press("escape")

    asyncio.run(interact())


@pytest.mark.parametrize("missing_key", [False, True])
def test_tk_reordered_keys_sync_only_complete_composite_keys(monkeypatch, missing_key):
    pytest.importorskip("tkinter")
    from execsql.gui import desktop
    from tests.gui.test_desktop_dialogs import _install_fake_tk, _mk_widget

    tk, ttk, _ = _install_fake_tk()
    monkeypatch.setattr(desktop, "tk", tk)
    monkeypatch.setattr(desktop, "ttk", ttk)
    root = _mk_widget()
    left, right = _mk_widget(), _mk_widget()
    ttk.Treeview.side_effect = [left, right]
    left.get_children.return_value = ("left0", "left1", "left2")
    right.get_children.return_value = ("right0", "right1", "right2")
    left.focus.return_value = "left0"
    args = comparison_args()
    if missing_key:
        args["keylist"] = ["id", "missing"]

    def interact(win):
        if missing_key:
            left.bind.assert_not_called()
            right.bind.assert_not_called()
        else:
            next(c.args[1] for c in left.bind.call_args_list if c.args[0] == "<ButtonRelease-1>")(None)
            right.selection_set.assert_called_once_with("right2")
            right.see.assert_called_once_with("right2")

    root.wait_window.side_effect = interact
    desktop.CompareDialog(root, args)
