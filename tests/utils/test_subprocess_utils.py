"""A subprocess timeout retains the child stack needed to diagnose CI hangs."""

from __future__ import annotations

import sys

import pytest

from tests.subprocess_utils import run_with_traceback


def test_timeout_includes_the_child_stack(tmp_path):
    package = tmp_path / "execsql"
    package.mkdir()
    (package / "__init__.py").touch()
    (package / "__main__.py").write_text("import threading\nthreading.Event().wait(60)\n")
    with pytest.raises(AssertionError, match="CLI exceeded") as raised:
        run_with_traceback(
            [sys.executable, "-m", "execsql"],
            timeout=3,
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
    assert "__main__.py" in str(raised.value)
    assert "threading.py" in str(raised.value)
