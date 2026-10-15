"""MySQL's LOAD DATA path drops blank lines at the end of the file, as every other import path does.

``_data_length`` finds where the trailing blank lines start, reading the
file backwards as bytes; the integration suite checks the rows MySQL loads.
"""

from __future__ import annotations

import os

import pytest

from execsql.db.mysql import _copy_head, _data_length


# Explicit ids: a generated id would spell out the 200,000-newline case in
# full, and a test id that long stopped the CI jobs that print each one.
@pytest.mark.parametrize(
    ("data", "expected"),
    [
        pytest.param(b"a\n1\n", None, id="ends-with-one-newline"),
        pytest.param(b"a\n1", None, id="no-final-newline"),
        pytest.param(b"", None, id="empty-file"),
        pytest.param(b"a\n1\n\n\n", 4, id="trailing-blank-lines"),
        pytest.param(b"a\r\n1\r\n\r\n\r\n", 6, id="trailing-blank-lines-crlf"),
        # A blank line inside the data is an empty row, not trailing.
        pytest.param(b"a\n\n1\n", None, id="inner-blank-line"),
        # More trailing newlines than one read covers.
        pytest.param(b"a\n1\n" + b"\n" * 200_000, 4, id="trailing-blank-lines-past-one-read"),
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
