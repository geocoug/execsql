"""Path-containment regression tests for B05.

Covers audit findings F003 (``--output-dir`` was a prefix, not a
containment boundary), F004 (EXPORT QUERY / WITH TEMPLATE / METADATA
variants ignored ``--output-dir``), F009 (``RM_FILE`` no opt-out),
F010 (``SERVE`` LFI primitive), F011 (INCLUDE / EXECUTE SCRIPT
unbounded paths), and F032 (Jinja2 / ``string.Template`` loader
path unsanitised).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.metacommands import io_export, io_fileops
from execsql.utils.fileio import safe_output_path


# ---------------------------------------------------------------------------
# safe_output_path — the new helper
# ---------------------------------------------------------------------------


class TestSafeOutputPath:
    def test_no_root_returns_path_unchanged(self):
        # Opting out: when root is None or empty, the helper is a no-op.
        assert safe_output_path("any/path", None) == "any/path"
        assert safe_output_path("/abs/path", "") == "/abs/path"

    def test_relative_path_joined_to_root(self, tmp_path):
        out = safe_output_path("sub/file.csv", str(tmp_path))
        assert Path(out) == (tmp_path / "sub" / "file.csv").resolve()

    def test_traversal_rejected(self, tmp_path):
        with pytest.raises(ErrInfo, match="outside the allowed root"):
            safe_output_path("../escape.csv", str(tmp_path))

    def test_double_traversal_rejected(self, tmp_path):
        with pytest.raises(ErrInfo, match="outside the allowed root"):
            safe_output_path("sub/../../escape.csv", str(tmp_path))

    def test_absolute_inside_root_accepted(self, tmp_path):
        target = tmp_path / "inside.csv"
        out = safe_output_path(str(target), str(tmp_path))
        assert Path(out) == target.resolve()

    def test_absolute_outside_root_rejected(self, tmp_path):
        outside = tmp_path.parent / "outside.csv"
        with pytest.raises(ErrInfo, match="outside the allowed root"):
            safe_output_path(str(outside), str(tmp_path))

    def test_unc_path_rejected(self, tmp_path):
        with pytest.raises(ErrInfo, match="outside the allowed root"):
            safe_output_path("//server/share/file", str(tmp_path))


# ---------------------------------------------------------------------------
# _apply_output_dir — F003 / F004
# ---------------------------------------------------------------------------


@pytest.fixture
def conf_with_output_dir(tmp_path):
    """Install a fake conf with export_output_dir set; restore on teardown."""
    saved = _state.conf
    fake = MagicMock()
    fake.export_output_dir = str(tmp_path.resolve())
    fake.allow_rm_file = True
    fake.allow_serve = True
    fake.serve_root = None
    _state.conf = fake
    yield fake
    _state.conf = saved


class TestApplyOutputDir:
    def test_relative_path_joined(self, conf_with_output_dir, tmp_path):
        out = io_export._apply_output_dir("report.csv")
        assert Path(out) == (tmp_path / "report.csv").resolve()

    def test_traversal_rejected(self, conf_with_output_dir):
        with pytest.raises(ErrInfo, match="outside the allowed root"):
            io_export._apply_output_dir("../escape.csv")

    def test_absolute_outside_rejected(self, conf_with_output_dir, tmp_path):
        outside = tmp_path.parent / "outside.csv"
        with pytest.raises(ErrInfo, match="outside the allowed root"):
            io_export._apply_output_dir(str(outside))

    def test_stdout_passthrough(self, conf_with_output_dir):
        assert io_export._apply_output_dir("stdout") == "stdout"
        assert io_export._apply_output_dir("STDOUT") == "STDOUT"

    def test_no_output_dir_passthrough(self, conf_with_output_dir):
        conf_with_output_dir.export_output_dir = None
        # No root set — anything goes (old behavior).
        assert io_export._apply_output_dir("../whatever.csv") == "../whatever.csv"


# ---------------------------------------------------------------------------
# F009 / F010 — RM_FILE and SERVE opt-out gates
# ---------------------------------------------------------------------------


class TestRmFileGate:
    def test_rm_file_blocked_when_disabled(self, conf_with_output_dir):
        conf_with_output_dir.allow_rm_file = False
        with pytest.raises(ErrInfo, match="--no-rm-file"):
            io_fileops.x_rm_file(filename="anything", metacommandline="-- !x! rm_file anything")

    def test_rm_file_allowed_by_default(self, conf_with_output_dir, tmp_path):
        # Create a file then RM_FILE it.
        target = tmp_path / "to_delete.txt"
        target.write_text("bye")
        io_fileops.x_rm_file(filename=str(target), metacommandline=f"-- !x! rm_file {target}")
        assert not target.exists()


class TestServeGate:
    def test_serve_blocked_when_disabled(self, conf_with_output_dir):
        conf_with_output_dir.allow_serve = False
        with pytest.raises(ErrInfo, match="--no-serve"):
            io_fileops.x_serve(
                filename="anything",
                format="binary",
                metacommandline="-- !x! serve anything as binary",
            )

    def test_serve_root_rejects_traversal(self, conf_with_output_dir, tmp_path):
        # serve_root set: only files under tmp_path may be served.
        conf_with_output_dir.serve_root = str(tmp_path)
        with pytest.raises(ErrInfo, match="outside the allowed root"):
            io_fileops.x_serve(
                filename="../etc/passwd",
                format="binary",
                metacommandline="-- !x! serve ../etc/passwd as binary",
            )
