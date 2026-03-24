"""
Shared pytest fixtures for the execsql test suite.

Most modules that do real work (DataType subclasses, Column, DataTable, …)
lazily import ``execsql.state as _state`` inside method bodies and access
``_state.conf``.  The ``minimal_conf`` fixture (autouse=True) provides a
lightweight ``SimpleNamespace`` that satisfies those attribute lookups without
requiring a full ConfigData / database initialisation.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

import execsql.state as _state


@pytest.fixture(autouse=True)
def minimal_conf():
    """
    Reset all module-level state, then set _state.conf to a SimpleNamespace
    covering all attributes accessed by the pure modules (types, models,
    parser, …).

    State is fully reset before and after every test so that nothing leaks
    between tests.
    """
    _state.reset()
    _state.conf = SimpleNamespace(
        # DT_Boolean
        boolean_int=True,
        boolean_words=False,
        # DT_Integer
        max_int=2_147_483_647,
        # Column / DataTable
        only_strings=False,
        trim_strings=False,
        replace_newlines=False,
        empty_strings=True,
        del_empty_cols=False,
        # File I/O / exporters
        output_encoding="utf-8",
        make_export_dirs=False,
        enc_err_disposition=None,
        # GUI
        gui_level=0,
        gui_framework="tkinter",
        gui_wait_on_exit=False,
        gui_wait_on_error_halt=False,
    )
    yield _state.conf
    _state.reset()


@pytest.fixture
def noop_filewriter_close():
    """
    Patch _state.filewriter_close (and the re-export in utils.fileio) to a
    no-op so that exporter tests never block waiting on the FileWriter
    subprocess.
    """
    with (
        patch("execsql.state.filewriter_close", return_value=None),
        patch("execsql.utils.fileio.filewriter_close", return_value=None),
    ):
        yield
