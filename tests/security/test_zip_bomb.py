"""B15/F031 regression: ``check_zip_decompression_ratio`` refuses to
open XLSX files that look like decompression bombs.

A malicious ``.xlsx`` can pack a 1 GB uncompressed member that
compresses to a few KB. ``openpyxl.load_workbook`` would happily
allocate memory proportional to the uncompressed size; the new
helper inspects the zip directory before any parsing happens and
raises :class:`ErrInfo` for high-ratio or excessively-large members.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from execsql.exceptions import ErrInfo
from execsql.utils.fileio import check_zip_decompression_ratio


def _make_zip(path: Path, member_data: bytes, member_name: str = "payload.xml") -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member_name, member_data)


class TestCheckZipDecompressionRatio:
    def test_legitimate_workbook_passes(self, tmp_path):
        """A normally-compressed workbook is accepted."""
        p = tmp_path / "ok.xlsx"
        _make_zip(p, b"<xml>some legitimate content</xml>" * 100)
        # Should not raise.
        check_zip_decompression_ratio(p)

    def test_non_zip_is_noop(self, tmp_path):
        """Legacy .xls is OLE-CDF, not zip — helper silently passes."""
        p = tmp_path / "ole.xls"
        p.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 1024)
        check_zip_decompression_ratio(p)

    def test_high_ratio_member_rejected(self, tmp_path):
        """One highly-compressible member > the per-member ratio is rejected."""
        p = tmp_path / "bomb.xlsx"
        # 1 MB of zeros compresses to a few KB → ratio ~1000:1
        _make_zip(p, b"\x00" * (1024 * 1024))
        with pytest.raises(ErrInfo, match="zip-bomb"):
            check_zip_decompression_ratio(p, max_ratio=100)

    def test_total_size_limit_rejected(self, tmp_path):
        """Aggregate uncompressed size > limit is rejected even if no
        individual ratio is suspicious."""
        p = tmp_path / "big.xlsx"
        # 5 MB of mostly-incompressible data so the ratio stays low.
        import os as _os

        _make_zip(p, _os.urandom(5 * 1024 * 1024))
        with pytest.raises(ErrInfo, match="possible zip-bomb"):
            check_zip_decompression_ratio(p, max_uncompressed_mb=2, max_ratio=10000)

    def test_high_ratio_within_max_ratio_allowed(self, tmp_path):
        """A high ratio is fine when within the configured tolerance."""
        p = tmp_path / "loose.xlsx"
        _make_zip(p, b"\x00" * 1024)
        # Set ratio cap very high so this passes.
        check_zip_decompression_ratio(p, max_ratio=100_000)


class TestDefusedXmlAvailable:
    """B15/F030: defusedxml is in the [formats] extra and gets defused
    on first OdsFile() construction."""

    def test_defusedxml_import(self):
        import defusedxml  # noqa: F401

    def test_odsfile_defuses_stdlib_on_init(self):
        """Constructing an OdsFile triggers defusedxml.defuse_stdlib()."""
        pytest.importorskip("odf")
        from execsql.exporters.ods import OdsFile

        # Construction should succeed (defuse is wrapped in try/except).
        OdsFile()
        # After init, defusedxml has monkey-patched xml.sax.* etc.
        import xml.sax
        import defusedxml.sax

        # The make_parser function on xml.sax is replaced with the
        # defused version (this is what defuse_stdlib does).
        assert xml.sax.make_parser is defusedxml.sax.make_parser
