"""B18/F012: IMPORT … PATTERN metacommands surface a friendly error
for malformed regular expressions instead of letting an uncaught
``re.error`` bubble up from ``re.compile``.

ReDoS via catastrophic backtracking remains a documented risk (re2
is not part of stdlib so we can't enforce a complexity cap here);
this batch only covers the syntax-error path.
"""

from __future__ import annotations

import pytest

from execsql.exceptions import ErrInfo
from execsql.metacommands.io_import import x_import_ods_pattern, x_import_xls_pattern


class TestImportPatternRegexErrors:
    def test_ods_pattern_invalid_regex_raises_errinfo(self):
        with pytest.raises(ErrInfo, match="Invalid regular expression"):
            x_import_ods_pattern(
                patn="[unclosed",
                new=None,
                schema=None,
                filename="any.ods",
                skip=None,
                metacommandline="IMPORT ODS PATTERN [unclosed",
            )

    def test_xls_pattern_invalid_regex_raises_errinfo(self):
        with pytest.raises(ErrInfo, match="Invalid regular expression"):
            x_import_xls_pattern(
                patn="(?P<unfinished>",
                new=None,
                schema=None,
                filename="any.xlsx",
                skip=None,
                encoding=None,
                metacommandline="IMPORT XLS PATTERN (?P<unfinished>",
            )

    def test_ods_pattern_error_includes_pattern(self):
        """The error message names the offending pattern so the user
        can spot the typo without inspecting the script."""
        try:
            x_import_ods_pattern(
                patn="bad[",
                new=None,
                schema=None,
                filename="any.ods",
                skip=None,
                metacommandline="-- !x! IMPORT ODS PATTERN bad[",
            )
        except ErrInfo as e:
            assert "bad[" in str(e)
        else:
            pytest.fail("Expected ErrInfo to be raised")
