"""
Tests for execsql.exporters.feather — Apache Feather format export.

Covers write_query_to_feather and write_query_to_hdf5 (via mocked tables),
as well as ImportError handling for missing optional dependencies.
The write_query_to_feather tests require ``polars`` and are skipped if it is
not installed.  The HDF5 and ImportError tests run without any optional deps.
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.types import DT_Decimal, DT_Float, DT_Integer, DT_Long, DT_Text, DT_Varchar

pl = pytest.importorskip("polars")

from execsql.exporters.feather import write_query_to_feather


# ---------------------------------------------------------------------------
# write_query_to_feather
# ---------------------------------------------------------------------------


class TestWriteQueryToFeather:
    def test_creates_file(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.feather")
        write_query_to_feather(out, ["id", "name"], iter([(1, "Alice"), (2, "Bob")]))
        assert (tmp_path / "out.feather").exists()

    def test_roundtrip_data(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.feather")
        rows = [(1, "Alice"), (2, "Bob")]
        write_query_to_feather(out, ["id", "name"], iter(rows))
        result = pl.read_ipc(out).to_dict(as_series=False)
        assert result["id"] == [1, 2]
        assert result["name"] == ["Alice", "Bob"]

    def test_empty_rows(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.feather")
        write_query_to_feather(out, ["id", "name"], iter([]))
        result = pl.read_ipc(out).to_dict(as_series=False)
        assert result["id"] == []

    def test_single_column(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.feather")
        write_query_to_feather(out, ["val"], iter([(42,), (99,)]))
        result = pl.read_ipc(out).to_dict(as_series=False)
        assert result["val"] == [42, 99]

    def test_none_values(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.feather")
        write_query_to_feather(out, ["id", "val"], iter([(1, None)]))
        result = pl.read_ipc(out).to_dict(as_series=False)
        assert result["id"] == [1]
        assert result["val"][0] is None

    def test_multiple_rows(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.feather")
        rows = [(i, f"item_{i}") for i in range(100)]
        write_query_to_feather(out, ["id", "label"], iter(rows))
        result = pl.read_ipc(out).to_dict(as_series=False)
        assert len(result["id"]) == 100
        assert result["id"][0] == 0
        assert result["label"][99] == "item_99"


# ---------------------------------------------------------------------------
# write_query_to_feather — ImportError handling
# ---------------------------------------------------------------------------


class TestWriteQueryToFeatherImportError:
    """write_query_to_feather raises ErrInfo when polars is not available."""

    def test_raises_errinfo_when_polars_missing(self, noop_filewriter_close, tmp_path):
        out = str(tmp_path / "out.feather")
        with patch.dict(sys.modules, {"polars": None}):
            # Re-import so the guarded import inside the function fires
            import importlib

            import execsql.exporters.feather as feather_mod

            importlib.reload(feather_mod)
            with pytest.raises(ErrInfo):
                feather_mod.write_query_to_feather(out, ["id"], iter([(1,)]))


# ---------------------------------------------------------------------------
# write_query_to_hdf5 — mocked tables library
# ---------------------------------------------------------------------------


def _build_fake_tables_module():
    """Return a fake `tables` module whose column constructors record their calls."""
    tables = ModuleType("tables")

    # Column type sentinels — each callable returns a unique sentinel string
    tables.StringCol = lambda size: f"StringCol({size})"
    tables.IntCol = lambda: "IntCol()"
    tables.Float64Col = lambda: "Float64Col()"
    tables.BoolCol = lambda: "BoolCol()"

    # Fake open_file returns a context-manager-like object
    h5row = MagicMock()
    h5row.__setitem__ = MagicMock()

    h5tbl = MagicMock()
    h5tbl.row = h5row

    h5grp = MagicMock()

    h5file = MagicMock()
    h5file.create_group = MagicMock(return_value=h5grp)
    h5file.create_table = MagicMock(return_value=h5tbl)
    h5file.close = MagicMock()

    tables.open_file = MagicMock(return_value=h5file)
    tables._h5file = h5file
    tables._h5tbl = h5tbl
    tables._h5row = h5row

    return tables


def _make_fake_db(headers, rows):
    """Return a SimpleNamespace that mimics the minimal db interface used by write_query_to_hdf5."""
    # select_rowsource is called twice: once for type inference, once for data
    call_count = [0]

    def select_rowsource(stmt):
        call_count[0] += 1
        return headers, iter(rows)

    return SimpleNamespace(select_rowsource=select_rowsource)


@pytest.fixture()
def state_with_dt_types(minimal_conf):
    """Extend _state.conf with hdf5_text_len and set DT_* class attributes on _state."""
    minimal_conf.hdf5_text_len = 1000
    # feather.py accesses these as _state.DT_Varchar etc.
    _state.DT_Varchar = DT_Varchar
    _state.DT_Text = DT_Text
    _state.DT_Integer = DT_Integer
    _state.DT_Long = DT_Long
    _state.DT_Float = DT_Float
    _state.DT_Decimal = DT_Decimal
    _state.DT_Time = type("DT_Time", (), {})  # placeholder sentinel
    yield minimal_conf
    # Cleanup: remove the attributes we added
    for attr in ("DT_Varchar", "DT_Text", "DT_Integer", "DT_Long", "DT_Float", "DT_Decimal", "DT_Time"):
        try:
            delattr(_state, attr)
        except AttributeError:
            pass


class TestWriteQueryToHdf5:
    """Tests for write_query_to_hdf5 with a mocked tables library."""

    def _run(self, headers, rows, outfile, fake_tables, append=False, desc=None):
        """Patch tables and filewriter_close, then call write_query_to_hdf5."""
        from execsql.exporters.feather import write_query_to_hdf5

        db = _make_fake_db(headers, rows)
        with (
            patch.dict(sys.modules, {"tables": fake_tables}),
            patch("execsql.exporters.feather.filewriter_close", return_value=None),
        ):
            write_query_to_hdf5("mytable", "SELECT 1", db, outfile, append=append, desc=desc)
        return fake_tables

    def test_opens_hdf5_file_in_write_mode(self, state_with_dt_types, tmp_path):
        """write_query_to_hdf5 opens the HDF5 file with mode 'w' when append=False."""
        fake_tables = _build_fake_tables_module()
        outfile = str(tmp_path / "out.h5")
        headers = ["id"]
        rows = [(1,), (2,)]
        self._run(headers, rows, outfile, fake_tables, append=False)
        fake_tables.open_file.assert_called_once_with(outfile, mode="w")

    def test_opens_hdf5_file_in_append_mode(self, state_with_dt_types, tmp_path):
        """write_query_to_hdf5 opens the HDF5 file with mode 'a' when append=True."""
        fake_tables = _build_fake_tables_module()
        outfile = str(tmp_path / "out.h5")
        headers = ["id"]
        rows = [(1,)]
        self._run(headers, rows, outfile, fake_tables, append=True)
        fake_tables.open_file.assert_called_once_with(outfile, mode="a")

    def test_creates_group_with_table_name(self, state_with_dt_types, tmp_path):
        """write_query_to_hdf5 creates the HDF5 group using the table name."""
        fake_tables = _build_fake_tables_module()
        outfile = str(tmp_path / "out.h5")
        headers = ["id"]
        rows = [(1,)]
        self._run(headers, rows, outfile, fake_tables)
        fake_tables._h5file.create_group.assert_called_once_with("/", "mytable", title=None)

    def test_creates_group_with_description(self, state_with_dt_types, tmp_path):
        """write_query_to_hdf5 passes desc as title to create_group."""
        fake_tables = _build_fake_tables_module()
        outfile = str(tmp_path / "out.h5")
        headers = ["id"]
        rows = [(1,)]
        self._run(headers, rows, outfile, fake_tables, desc="My table description")
        fake_tables._h5file.create_group.assert_called_once_with("/", "mytable", title="My table description")

    def test_closes_hdf5_file_after_writing(self, state_with_dt_types, tmp_path):
        """write_query_to_hdf5 closes the HDF5 file when done."""
        fake_tables = _build_fake_tables_module()
        outfile = str(tmp_path / "out.h5")
        headers = ["id"]
        rows = [(1,)]
        self._run(headers, rows, outfile, fake_tables)
        fake_tables._h5file.close.assert_called_once()

    def test_flushes_table_after_writing_rows(self, state_with_dt_types, tmp_path):
        """write_query_to_hdf5 flushes the HDF5 table after writing all rows."""
        fake_tables = _build_fake_tables_module()
        outfile = str(tmp_path / "out.h5")
        headers = ["id"]
        rows = [(1,), (2,)]
        self._run(headers, rows, outfile, fake_tables)
        fake_tables._h5tbl.flush.assert_called_once()

    def test_integer_column_maps_to_intcol(self, state_with_dt_types, tmp_path):
        """Integer columns are mapped to IntCol in the type dictionary."""
        fake_tables = _build_fake_tables_module()
        outfile = str(tmp_path / "out.h5")
        headers = ["count"]
        rows = [(1,), (2,), (3,)]
        self._run(headers, rows, outfile, fake_tables)
        # create_table receives the type dict; we just verify it was called
        fake_tables._h5file.create_table.assert_called_once()
        type_dict = fake_tables._h5file.create_table.call_args[0][2]
        assert type_dict["count"] == "IntCol()"

    def test_float_column_maps_to_float64col(self, state_with_dt_types, tmp_path):
        """Float columns are mapped to Float64Col in the type dictionary."""
        fake_tables = _build_fake_tables_module()
        outfile = str(tmp_path / "out.h5")
        headers = ["score"]
        rows = [(1.5,), (2.7,)]
        self._run(headers, rows, outfile, fake_tables)
        type_dict = fake_tables._h5file.create_table.call_args[0][2]
        assert type_dict["score"] == "Float64Col()"

    def test_boolean_column_maps_to_boolcol(self, state_with_dt_types, tmp_path):
        """Boolean columns are mapped to BoolCol in the type dictionary."""
        fake_tables = _build_fake_tables_module()
        outfile = str(tmp_path / "out.h5")
        headers = ["flag"]
        rows = [(True,), (False,)]
        self._run(headers, rows, outfile, fake_tables)
        type_dict = fake_tables._h5file.create_table.call_args[0][2]
        assert type_dict["flag"] == "BoolCol()"

    def test_varchar_column_maps_to_stringcol(self, state_with_dt_types, tmp_path):
        """Varchar columns are mapped to StringCol in the type dictionary."""
        fake_tables = _build_fake_tables_module()
        outfile = str(tmp_path / "out.h5")
        headers = ["name"]
        rows = [("Alice",), ("Bob",)]
        self._run(headers, rows, outfile, fake_tables)
        type_dict = fake_tables._h5file.create_table.call_args[0][2]
        # StringCol takes a size argument based on max string length
        assert type_dict["name"].startswith("StringCol(")

    def test_date_column_casts_to_string(self, state_with_dt_types, tmp_path):
        """Date/timestamp columns are stored as strings (cast_flags True)."""
        import datetime

        fake_tables = _build_fake_tables_module()
        outfile = str(tmp_path / "out.h5")
        headers = ["created"]
        rows = [(datetime.date(2024, 1, 15),), (datetime.date(2024, 6, 1),)]
        self._run(headers, rows, outfile, fake_tables)
        type_dict = fake_tables._h5file.create_table.call_args[0][2]
        # Date columns map to StringCol(50)
        assert type_dict["created"] == "StringCol(50)"

    def test_db_select_exception_raised_as_errinfo(self, state_with_dt_types, tmp_path):
        """A database error from select_rowsource is re-raised as ErrInfo."""
        fake_tables = _build_fake_tables_module()
        outfile = str(tmp_path / "out.h5")

        def bad_db_select(stmt):
            raise RuntimeError("DB gone away")

        bad_db = SimpleNamespace(select_rowsource=bad_db_select)

        from execsql.exporters.feather import write_query_to_hdf5

        with (
            patch.dict(sys.modules, {"tables": fake_tables}),
            patch("execsql.exporters.feather.filewriter_close", return_value=None),
            pytest.raises(ErrInfo),
        ):
            write_query_to_hdf5("t", "SELECT 1", bad_db, outfile)

    def test_db_errinfo_propagates_unchanged(self, state_with_dt_types, tmp_path):
        """An ErrInfo raised by the db is re-raised as-is (not wrapped)."""
        fake_tables = _build_fake_tables_module()
        outfile = str(tmp_path / "out.h5")
        original = ErrInfo("db", other_msg="original error")

        def errinfo_db(stmt):
            raise original

        bad_db = SimpleNamespace(select_rowsource=errinfo_db)

        from execsql.exporters.feather import write_query_to_hdf5

        with (
            patch.dict(sys.modules, {"tables": fake_tables}),
            patch("execsql.exporters.feather.filewriter_close", return_value=None),
            pytest.raises(ErrInfo) as exc_info,
        ):
            write_query_to_hdf5("t", "SELECT 1", bad_db, outfile)
        assert exc_info.value is original


# ---------------------------------------------------------------------------
# write_query_to_hdf5 — ImportError handling
# ---------------------------------------------------------------------------


class TestWriteQueryToHdf5ImportError:
    """write_query_to_hdf5 raises ErrInfo when tables is not available."""

    def test_raises_errinfo_when_tables_missing(self, state_with_dt_types, tmp_path):
        """write_query_to_hdf5 raises ErrInfo with helpful message when tables is absent."""
        from execsql.exporters.feather import write_query_to_hdf5

        fake_db = SimpleNamespace(select_rowsource=lambda s: (["id"], iter([(1,)])))

        with (
            patch.dict(sys.modules, {"tables": None}),
            pytest.raises(ErrInfo) as exc_info,
        ):
            write_query_to_hdf5("t", "SELECT 1", fake_db, str(tmp_path / "out.h5"))

        assert "tables" in str(exc_info.value).lower() or "hdf5" in str(exc_info.value).lower()
