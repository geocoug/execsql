"""Package-level smoke tests — import hygiene and version string."""

from __future__ import annotations

import importlib
import re
from unittest.mock import patch


def test_version_string_format():
    import execsql

    assert re.match(r"^\d+\.\d+\.\d+$", execsql.__version__), (
        f"__version__ {execsql.__version__!r} does not match semver format"
    )


def test_main_module_importable():
    """python -m execsql entry point resolves without error."""
    import execsql.__main__  # noqa: F401


def test_cli_importable():
    from execsql.cli import app, _legacy_main

    assert callable(_legacy_main)
    assert app is not None


def test_state_importable():
    import execsql.state as _state

    # Core attributes are present at module level before main() runs.
    assert hasattr(_state, "commandliststack")
    assert hasattr(_state, "subvars")
    assert hasattr(_state, "varlike")


def test_version_fallback_when_package_not_found():
    """__version__ falls back to 'unknown' when package metadata is missing (lines 15-16)."""
    from importlib.metadata import PackageNotFoundError

    import execsql

    with patch("importlib.metadata.version", side_effect=PackageNotFoundError("execsql2")):
        # Re-execute the try/except block by reloading the module
        importlib.reload(execsql)
        assert execsql.__version__ == "unknown"

    # Restore to real version
    importlib.reload(execsql)
