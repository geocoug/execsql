"""Folding: blocks up to their closing line, IF branches separately, multi-line SQL and comments."""

from __future__ import annotations

import pytest

pytest.importorskip("pygls")

from lsprotocol import types  # noqa: E402

from execsql.lsp.folding import folding_ranges  # noqa: E402

SCRIPT = """\
-- Load the orders.
-- Run after setup.sql.
-- !x! IF(hasrows(orders))
SELECT 1;
-- !x! ELSEIF(hasrows(returns))
SELECT 2;
-- !x! ELSE
SELECT 3;
-- !x! ENDIF
-- !x! BEGIN SCRIPT load(t)
SELECT *
  FROM !!#t!!;
-- !x! END SCRIPT
-- !x! LOOP WHILE(False)
SELECT 4;
-- !x! END LOOP
SELECT 5;
"""


def _ranges(text: str = SCRIPT) -> list[tuple[int, int, str | None]]:
    return [(r.start_line, r.end_line, r.kind) for r in folding_ranges(text, None)]


def test_each_kind_of_range():
    assert _ranges() == [
        (0, 1, types.FoldingRangeKind.Comment),  # the comment lines
        (2, 3, None),  # IF .. the line before ELSEIF
        (4, 5, None),  # ELSEIF .. the line before ELSE
        (6, 7, None),  # ELSE .. the line before ENDIF
        (9, 11, None),  # BEGIN SCRIPT .. the line before END SCRIPT
        (10, 11, None),  # the two-line SELECT inside it
        (13, 14, None),  # LOOP .. the line before END LOOP
    ]


def test_an_if_without_branches_folds_to_the_line_before_endif():
    assert _ranges("-- !x! IF(True)\nSELECT 1;\nSELECT 2;\n-- !x! ENDIF\n") == [(0, 2, None)]


def test_single_lines_do_not_fold():
    assert _ranges("SELECT 1;\n-- one comment\n-- !x! IF(True)\n-- !x! ENDIF\n") == []


def test_an_unclosed_block_folds_to_its_last_line():
    assert _ranges("-- !x! IF(True)\nSELECT 1;\nSELECT 2;\nSELECT 3;\n") == [(0, 3, None)]


def test_an_unclosed_block_ending_in_a_metacommand_folds_to_its_last_line():
    assert _ranges("-- !x! IF(True)\nSELECT 1;\n-- !x! WRITE done\n") == [(0, 2, None)]
