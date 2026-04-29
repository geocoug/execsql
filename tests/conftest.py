"""
Shared pytest fixtures for the execsql test suite.

Most modules that do real work (DataType subclasses, Column, DataTable, …)
lazily import ``execsql.state as _state`` inside method bodies and access
``_state.conf``.  The ``minimal_conf`` fixture (autouse=True) provides a
lightweight ``SimpleNamespace`` that satisfies those attribute lookups without
requiring a full ConfigData / database initialisation.
"""

from __future__ import annotations

import contextlib
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
        empty_rows=True,
        del_empty_cols=False,
        create_col_hdrs=False,
        trim_col_hdrs="none",
        clean_col_hdrs=False,
        fold_col_hdrs="no",
        dedup_col_hdrs=False,
        # File I/O / exporters
        output_encoding="utf-8",
        import_encoding="utf-8",
        script_encoding="utf8",
        make_export_dirs=False,
        export_output_dir=None,
        enc_err_disposition=None,
        quote_all_text=False,
        # Write hooks
        write_warnings=False,
        write_prefix=None,
        write_suffix=None,
        # CSS
        css_file=None,
        css_styles=None,
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
    Patch filewriter_close in each exporter/importer module that imports it
    directly, so that tests never block waiting on the FileWriter subprocess.
    """
    targets = [
        "execsql.utils.fileio.filewriter_close",
        "execsql.exporters.delimited.filewriter_close",
        "execsql.exporters.feather.filewriter_close",
        "execsql.exporters.parquet.filewriter_close",
        "execsql.exporters.html.filewriter_close",
        "execsql.exporters.json.filewriter_close",
        "execsql.exporters.latex.filewriter_close",
        "execsql.exporters.ods.filewriter_close",
        "execsql.exporters.pretty.filewriter_close",
        "execsql.exporters.raw.filewriter_close",
        "execsql.exporters.templates.filewriter_close",
        "execsql.exporters.values.filewriter_close",
        "execsql.exporters.xml.filewriter_close",
        "execsql.exporters.markdown.filewriter_close",
        "execsql.exporters.yaml.filewriter_close",
    ]
    with contextlib.ExitStack() as stack:
        for target in targets:
            try:
                stack.enter_context(patch(target, return_value=None))
            except AttributeError:
                pass
        yield
