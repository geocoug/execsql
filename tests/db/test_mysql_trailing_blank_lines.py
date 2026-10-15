"""MySQL's LOAD DATA path drops blank lines at the end of the file, as every other import path does.

``_data_length`` finds where the trailing blank lines start, reading the
file backwards as bytes; the integration suite checks the rows MySQL loads.
"""

from __future__ import annotations

import os

import pytest

from execsql.db.mysql import _copy_head, _data_length


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"a\n1\n", None),
        (b"a\n1", None),
        (b"", None),
        (b"a\n1\n\n\n", 4),
        (b"a\r\n1\r\n\r\n\r\n", 6),
        (b"a\n\n1\n", None),  # a blank line inside the data is an empty row, not trailing
        (b"a\n1\n" + b"\n" * 200_000, 4),  # more trailing newlines than one read
    ],
)
def test_data_length(tmp_path, data, expected):
    path = tmp_path / "f.csv"
    path.write_bytes(data)
    assert _data_length(str(path)) == expected


def test_copy_head_copies_the_data_lines_only(tmp_path):
    path = tmp_path / "f.csv"
    path.write_bytes(b"a,b\n1,x\n\n\n")
    copy = _copy_head(str(path), 8)
    try:
        with open(copy, "rb") as f:
            assert f.read() == b"a,b\n1,x\n"
    finally:
        os.unlink(copy)
