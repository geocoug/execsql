"""B11/F049 regression: ``EncodedFile`` now supports the context-manager
protocol so callers can use ``with EncodedFile(...) as fh:``.
"""

from __future__ import annotations

import pytest

from execsql.utils.fileio import EncodedFile


@pytest.fixture
def conf_for_io():
    """Install just enough conf state for EncodedFile.open() to work."""
    import execsql.state as _state

    saved = _state.conf
    fake = type("c", (), {"enc_err_disposition": "strict"})()
    _state.conf = fake
    yield fake
    _state.conf = saved


def test_context_manager_opens_and_closes(tmp_path, conf_for_io):
    p = tmp_path / "in.txt"
    p.write_text("hello\nworld\n", encoding="utf-8")
    ef = EncodedFile(str(p), "utf-8")
    with ef as fh:
        contents = fh.read()
    assert contents == "hello\nworld\n"
    # close() set fo back to None; calling close again is a no-op.
    assert ef.fo is None


def test_context_manager_closes_on_exception(tmp_path, conf_for_io):
    p = tmp_path / "boom.txt"
    p.write_text("data", encoding="utf-8")
    ef = EncodedFile(str(p), "utf-8")
    with pytest.raises(RuntimeError, match="boom"), ef:
        raise RuntimeError("boom")
    # Exception didn't leak the handle.
    assert ef.fo is None


def test_close_idempotent(tmp_path, conf_for_io):
    p = tmp_path / "again.txt"
    p.write_text("x", encoding="utf-8")
    ef = EncodedFile(str(p), "utf-8")
    ef.open("r")
    ef.close()
    ef.close()  # Second close must not raise.
    assert ef.fo is None
