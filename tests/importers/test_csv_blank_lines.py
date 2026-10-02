"""A blank line in a delimited file is an empty row, not the end of the file.

Both CSV readers used to stop at the first blank line, so every row after it
was dropped and the import still succeeded.  PostgreSQL's COPY path reads the
raw file and rejected the blank line outright.  A blank line inside the data
is now an all-NULL row, which ``CONFIG EMPTY_ROWS`` keeps (the default) or
drops, as it does for a row of empty fields.  Blank lines at the end of the
file still end it.
"""

from __future__ import annotations

import pytest

from execsql.exporters.delimited import CsvFile, blank_lines_as_empty_rows

HEADER = ["a", "b"]
ROWS = [["1", "x"], ["2", "y"], ["3", "z"], ["4", "w"]]
WITH_EMPTY = [["1", "x"], ["2", "y"], [None, None], ["3", "z"], ["4", "w"]]


@pytest.fixture(autouse=True)
def reader_conf(minimal_conf):
    minimal_conf.del_empty_cols = False
    minimal_conf.import_encoding = "utf-8"
    minimal_conf.scan_lines = 50
    yield minimal_conf


def _read(path, *lineformat):
    f = CsvFile(str(path), "utf-8")
    if lineformat:
        f.lineformat(*lineformat)
    return list(f.reader())


# A backslash escape character sends the file to the character-level reader.
READERS = pytest.mark.parametrize("lineformat", [(",", '"', None), (",", '"', "\\")], ids=["fast", "slow"])


class TestReaders:
    @READERS
    def test_a_blank_line_is_an_empty_row(self, tmp_path, lineformat):
        path = tmp_path / "b.csv"
        path.write_text('a,b\n1,"x"\n2,"y"\n\n3,"z"\n4,"w"\n')
        assert _read(path, *lineformat) == [HEADER, *WITH_EMPTY]

    @READERS
    def test_blank_lines_at_the_end_or_before_the_header_add_no_rows(self, tmp_path, lineformat):
        path = tmp_path / "b.csv"
        path.write_text("\na,b\n1,x\n2,y\n3,z\n4,w\n\n\n")
        assert _read(path, *lineformat) == [HEADER, *ROWS]

    @READERS
    def test_each_blank_line_is_its_own_row(self, tmp_path, lineformat):
        path = tmp_path / "b.csv"
        path.write_text("a,b\n1,x\n\n\n2,y\n")
        assert _read(path, *lineformat) == [HEADER, ["1", "x"], [None, None], [None, None], ["2", "y"]]


class TestCopyStream:
    def _stream(self, text, columns=2, size=4):
        import io

        return "".join(blank_lines_as_empty_rows(io.StringIO(text), ",", '"', columns, size))

    def test_a_blank_line_between_records_becomes_empty_fields(self):
        assert self._stream("1,x\n\n2,y\n", columns=3) == "1,x\n,,\n2,y\n"

    def test_blank_lines_at_the_end_are_dropped(self):
        assert self._stream("1,x\n2,y\n\n\n") == "1,x\n2,y\n"

    def test_a_blank_line_inside_a_quoted_value_is_kept(self):
        text = '1,"first\n\nthird"\n\n2,"a ""quoted"" word"\n'
        assert self._stream(text) == '1,"first\n\nthird"\n,\n2,"a ""quoted"" word"\n'


@pytest.mark.parametrize("dbms", ["sqlite", "duckdb", "postgres"])
@pytest.mark.parametrize(
    "content",
    ["a,b\n1,x\n2,y\n\n3,z\n4,w\n", '"a","b"\n1,"x"\n2,"y"\n\n3,"z"\n4,"w"\n'],
    ids=["unquoted", "quoted"],
)
@pytest.mark.parametrize(("empty_rows", "expected"), [("YES", WITH_EMPTY), ("NO", ROWS)], ids=["keep", "drop"])
def test_empty_rows_setting_decides(tmp_path, dbms, content, empty_rows, expected):
    """Unquoted files take the row path everywhere; quoted ones take COPY on PostgreSQL when empty rows are kept."""
    from execsql import run
    from tests.live_db import open_backend

    db = open_backend(dbms, tmp_path)
    csv = tmp_path / "blank_lines.csv"
    csv.write_text(content)
    try:
        result = run(
            sql=f"-- !x! CONFIG EMPTY_ROWS {empty_rows}\n-- !x! IMPORT TO REPLACEMENT blank_lines_t FROM {csv}\n",
            connection=db,
        )
        assert result.success, result.errors
        _, rows = db.select_data("select a, b from blank_lines_t")
        got = [[None if v is None else str(v) for v in r] for r in rows]
        key = lambda r: [v or "" for v in r]  # noqa: E731
        assert sorted(got, key=key) == sorted(expected, key=key)
    finally:
        try:
            db.execute("drop table if exists blank_lines_t")
            db.commit()
        finally:
            db.close()
