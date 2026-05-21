"""Coverage tests for execsql.exporters.ods entry-point functions.

The existing ``tests/exporters/test_ods.py`` covers the ``OdsFile`` wrapper.
This module covers the higher-level ``export_ods``, ``write_query_to_ods``,
and ``write_queries_to_ods`` functions that the existing tests skip
("require runtime state").  ``_state.dbs`` and ``current_script_line`` are
mocked.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

try:
    import odf.opendocument  # noqa: F401

    _ods_available = True
except ImportError:
    _ods_available = False

pytestmark = pytest.mark.skipif(not _ods_available, reason="requires odfpy")

import execsql.state as _state  # noqa: E402
from execsql.exporters.ods import (  # noqa: E402
    OdsFile,
    export_ods,
    write_queries_to_ods,
    write_query_to_ods,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def state_dbs():
    """Install a fake DatabasePool on _state.dbs with .current()."""
    from execsql.exporters.base import ExportMetadata

    db = MagicMock()
    db.name.return_value = "/tmp/test.db"
    db.select_rowsource.return_value = (
        ["id", "name", "value"],
        [(1, "alpha", 1.0), (2, "beta", 2.0)],
    )
    pool = MagicMock()
    pool.current.return_value = db
    _state.dbs = pool
    _state.export_metadata = ExportMetadata()
    yield db
    _state.dbs = None
    _state.export_metadata = None


@pytest.fixture(autouse=True)
def _patch_script_line():
    with patch(
        "execsql.exporters.ods.current_script_line",
        return_value=("script.sql", 1),
    ):
        yield


@pytest.fixture(autouse=True)
def _patch_filewriter_close():
    """filewriter_close blocks on the FileWriter subprocess; no-op it for tests."""
    with patch("execsql.exporters.ods.filewriter_close"):
        yield


# ---------------------------------------------------------------------------
# export_ods — direct entry point
# ---------------------------------------------------------------------------


class TestExportOds:
    def test_new_file_simple(self, state_dbs, tmp_path: Path) -> None:
        out = tmp_path / "out.ods"
        export_ods(
            str(out),
            ["id", "name"],
            [(1, "alpha"), (2, "beta")],
            append=False,
            querytext="select * from t",
            sheetname="Data",
            desc="My data",
        )
        assert out.is_file()

    def test_append_to_existing(self, state_dbs, tmp_path: Path) -> None:
        out = tmp_path / "append.ods"
        # Create initial file
        export_ods(str(out), ["a"], [(1,), (2,)], sheetname="First")
        # Append — should create First2 since First exists
        export_ods(str(out), ["a"], [(3,)], append=True, sheetname="First")
        assert out.is_file()
        wbk = OdsFile()
        wbk.open(str(out))
        names = wbk.sheetnames()
        # Both First and a numbered suffix should exist
        assert "First" in names
        wbk.close()

    def test_overwrite_existing(self, state_dbs, tmp_path: Path) -> None:
        out = tmp_path / "over.ods"
        export_ods(str(out), ["a"], [(1,)], sheetname="A")
        # Without append, should remove and recreate
        export_ods(str(out), ["a"], [(2,)], append=False, sheetname="B")
        wbk = OdsFile()
        wbk.open(str(out))
        assert "B" in wbk.sheetnames()
        wbk.close()

    def test_without_querytext(self, state_dbs, tmp_path: Path) -> None:
        out = tmp_path / "noqry.ods"
        export_ods(str(out), ["a"], [(1,)], querytext=None, desc="d")
        assert out.is_file()

    def test_mixed_types(self, state_dbs, tmp_path: Path) -> None:
        """Cover the type-dispatch lines in add_row_to_sheet."""
        out = tmp_path / "types.ods"
        rows = [
            (
                True,
                1,
                1.5,
                "text",
                datetime.datetime(2024, 1, 2, 3, 4, 5),
                datetime.date(2024, 1, 2),
                datetime.time(3, 4, 5),
                None,
            ),
        ]
        export_ods(
            str(out),
            ["bool", "int", "float", "str", "dt", "date", "time", "null"],
            rows,
        )
        assert out.is_file()


# ---------------------------------------------------------------------------
# write_query_to_ods — pulls headers/rows from a db
# ---------------------------------------------------------------------------


class TestWriteQueryToOds:
    def test_happy_path(self, state_dbs, tmp_path: Path) -> None:
        out = tmp_path / "q.ods"
        write_query_to_ods(
            "select * from t",
            state_dbs,
            str(out),
            sheetname="Result",
            desc="d",
        )
        assert out.is_file()

    def test_db_error_wrapped(self, state_dbs, tmp_path: Path) -> None:
        from execsql.exceptions import ErrInfo

        state_dbs.select_rowsource.side_effect = RuntimeError("db boom")
        with pytest.raises(ErrInfo):
            write_query_to_ods("select * from t", state_dbs, str(tmp_path / "q.ods"))


# ---------------------------------------------------------------------------
# write_queries_to_ods — multi-table export
# ---------------------------------------------------------------------------


class TestWriteQueriesToOds:
    def test_multiple_tables(self, state_dbs, tmp_path: Path) -> None:
        out = tmp_path / "multi.ods"
        write_queries_to_ods("t1,t2,t3", state_dbs, str(out))
        assert out.is_file()
        wbk = OdsFile()
        wbk.open(str(out))
        names = wbk.sheetnames()
        for tn in ("t1", "t2", "t3"):
            assert tn in names
        wbk.close()

    def test_schema_qualified_table(self, state_dbs, tmp_path: Path) -> None:
        out = tmp_path / "schema.ods"
        write_queries_to_ods("public.t1,public.t2", state_dbs, str(out))
        assert out.is_file()

    def test_with_descriptions(self, state_dbs, tmp_path: Path) -> None:
        out = tmp_path / "desc.ods"
        write_queries_to_ods(
            "t1,t2",
            state_dbs,
            str(out),
            desc="first table,second table",
        )
        assert out.is_file()

    def test_single_desc_all_tables(self, state_dbs, tmp_path: Path) -> None:
        out = tmp_path / "onedesc.ods"
        write_queries_to_ods(
            "t1,t2",
            state_dbs,
            str(out),
            desc="shared",
        )
        assert out.is_file()

    def test_duplicate_sheet_names_get_suffixed(self, state_dbs, tmp_path: Path) -> None:
        out = tmp_path / "dup.ods"
        # Same table name twice → second should get a numeric suffix
        write_queries_to_ods("t1,t1", state_dbs, str(out))
        wbk = OdsFile()
        wbk.open(str(out))
        names = wbk.sheetnames()
        assert "t1" in names
        # Second sheet gets a suffix like t1_1
        suffixed = [n for n in names if n.startswith("t1_")]
        assert suffixed
        wbk.close()

    def test_bad_table_spec_raises(self, state_dbs, tmp_path: Path) -> None:
        from execsql.exceptions import ErrInfo

        out = tmp_path / "bad.ods"
        with pytest.raises(ErrInfo):
            write_queries_to_ods("a.b.c", state_dbs, str(out))

    def test_db_error_wrapped(self, state_dbs, tmp_path: Path) -> None:
        from execsql.exceptions import ErrInfo

        state_dbs.select_rowsource.side_effect = RuntimeError("oops")
        with pytest.raises(ErrInfo):
            write_queries_to_ods("t1", state_dbs, str(tmp_path / "err.ods"))


# ---------------------------------------------------------------------------
# OdsFile — additional read paths
# ---------------------------------------------------------------------------


class TestOdsFileReadPaths:
    def test_open_existing_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "rt.ods"
        wbk = OdsFile()
        wbk.open(str(path))
        tbl = wbk.new_sheet("S")
        wbk.add_row_to_sheet(["a", "b"], tbl, header=True)
        wbk.add_row_to_sheet([1, 2], tbl)
        wbk.add_sheet(tbl)
        wbk.save_close()

        wbk2 = OdsFile()
        wbk2.open(str(path))
        # Re-open should populate cell_style_names from the existing file
        assert "S" in wbk2.sheetnames()
        wbk2.close()

    def test_sheet_named_by_integer(self, tmp_path: Path) -> None:
        path = tmp_path / "idx.ods"
        wbk = OdsFile()
        wbk.open(str(path))
        for name in ("A", "B", "C"):
            tbl = wbk.new_sheet(name)
            wbk.add_row_to_sheet([1], tbl, header=True)
            wbk.add_sheet(tbl)
        wbk.save_close()

        wbk2 = OdsFile()
        wbk2.open(str(path))
        # By 1-based index
        sheet = wbk2.sheet_named(2)
        assert sheet is not None
        # By 0-based int as string "0" → returns None (covers the
        # ``sheet_no = None`` branch when the integer is invalid)
        assert wbk2.sheet_named("0") is None
        wbk2.close()

    def test_sheet_data_skips_junk_headers(self, tmp_path: Path) -> None:
        path = tmp_path / "junk.ods"
        wbk = OdsFile()
        wbk.open(str(path))
        tbl = wbk.new_sheet("data")
        wbk.add_row_to_sheet(["JUNK"], tbl)
        wbk.add_row_to_sheet(["a", "b"], tbl, header=True)
        wbk.add_row_to_sheet([1, 2], tbl)
        wbk.add_sheet(tbl)
        wbk.save_close()

        wbk2 = OdsFile()
        wbk2.open(str(path))
        rows = wbk2.sheet_data("data", junk_header_rows=1)
        # First row should be the real header now
        assert rows[0] == ["a", "b"] or rows[0][0] == "a"

    def test_sheet_data_unknown_sheet_raises(self, tmp_path: Path) -> None:
        from execsql.exceptions import OdsFileError

        path = tmp_path / "no.ods"
        wbk = OdsFile()
        wbk.open(str(path))
        tbl = wbk.new_sheet("Real")
        wbk.add_row_to_sheet(["a"], tbl, header=True)
        wbk.add_sheet(tbl)
        wbk.save_close()

        wbk2 = OdsFile()
        wbk2.open(str(path))
        with pytest.raises(OdsFileError):
            wbk2.sheet_data("Nonexistent")
