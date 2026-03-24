"""
Tests for execsql.exporters.feather — Apache Feather format export.

Covers write_query_to_feather.  Requires ``polars``.
The entire module is skipped if polars is not installed.
"""

from __future__ import annotations

import pytest

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
