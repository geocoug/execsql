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
import sys
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
        exact_decimals=False,
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
        # Security
        allow_system_cmd=True,
    )
    yield _state.conf
    _state.reset()


@pytest.fixture
def noop_filewriter_close():
    """
    Patch filewriter_close in each exporter/importer module that imports it
    directly, so that tests never block waiting on the FileWriter thread.
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


@pytest.fixture(autouse=True)
def _restore_cwd():
    """Put the working directory back after every test.

    The ``CD`` metacommand changes the process working directory, and a test
    that exercises it leaves the whole session in a pytest ``tmp_path``. Every
    later test that names a file by a repo-relative path then fails — but only
    when the two run in that order, so with random ordering it surfaces as an
    intermittent failure somewhere unrelated. Restoring here fixes the class
    of bug rather than the one test that happened to expose it.
    """
    import os

    original = os.getcwd()
    try:
        yield
    finally:
        if os.getcwd() != original:
            os.chdir(original)


@pytest.fixture(autouse=True)
def _fresh_sigterm_state(monkeypatch):
    """Start every test with no SIGTERM held, pending or acted on.

    A test that calls the SIGTERM handler marks the run as terminated, and
    every ``SYSTEM_CMD`` after that in the same process would end at once.
    """
    import execsql.utils.sigterm as sigterm

    monkeypatch.setattr(sigterm, "_held", 0)
    monkeypatch.setattr(sigterm, "_pending", None)
    monkeypatch.setattr(sigterm, "_terminated", None)
    monkeypatch.setattr(sigterm, "_commands", [])


@pytest.fixture(autouse=True)
def _no_real_browser(monkeypatch):
    """Fail any test that would open a real browser tab.

    ``--online-help`` and the GUI Help buttons call ``webbrowser.open``. When a
    Typer/Click pairing misreads flags, that callback fires on every CLI
    invocation, and a test run opens one tab per test. In-process calls fail
    the test instead.

    Child processes (tests that run the real entry point) cannot be patched,
    so ``BROWSER`` points them at ``true``. It must be a bare executable:
    :mod:`webbrowser` runs it as ``[BROWSER, url]`` without splitting, and if
    it fails to launch, falls back to the user's real browser. Windows has no
    ``true``, so there only the in-process guard applies.
    """
    import shutil
    import webbrowser

    def _refuse(url, *args, **kwargs):
        pytest.fail(f"test tried to open a real browser: {url}")

    monkeypatch.setattr(webbrowser, "open", _refuse)
    monkeypatch.setattr(webbrowser, "open_new", _refuse)
    monkeypatch.setattr(webbrowser, "open_new_tab", _refuse)
    true = shutil.which("true")
    if true:
        monkeypatch.setenv("BROWSER", true)


def pytest_configure(config):
    """Build pywin32's COM cache before the xdist workers start.

    Every worker imports ``win32com.client`` as it collects
    ``tests/db/test_access_windows.py``.  On a fresh environment that import
    writes ``win32com/gen_py/dicts.dat``, and a worker that reads the file
    while another is writing it fails with ``EOFError: Ran out of input``.
    The controller (or a ``-n 0`` run) imports it first, so the workers find
    the file complete.
    """
    if sys.platform != "win32" or hasattr(config, "workerinput"):
        return
    # Any failure, not only a missing pywin32: a cache a killed run left half
    # written fails here too, and then only that module fails to collect.
    with contextlib.suppress(Exception):
        import win32com.client  # noqa: F401


#: Parameter values that name a live database server (see ``tests/live_db.py``
#: and the templates' ``target`` fixture).
_LIVE_SERVERS = frozenset({"postgres", "mysql", "mariadb", "sqlserver"})


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    """Put each test parametrized with a live server in that server's xdist group.

    Tests against one server share its database, and many reuse table names,
    so ``--dist loadgroup`` must hand them all to one worker. Modules that test
    one server throughout set ``pytestmark`` instead. ``tryfirst``: xdist reads
    the groups in its own ``pytest_collection_modifyitems``.
    """
    for item in items:
        callspec = getattr(item, "callspec", None)
        if callspec is None:
            continue
        for value in callspec.params.values():
            if isinstance(value, str) and value in _LIVE_SERVERS:
                item.add_marker(pytest.mark.xdist_group(f"live-{value}"))
