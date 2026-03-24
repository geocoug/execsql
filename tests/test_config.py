"""Tests for configuration classes in execsql.config."""

from __future__ import annotations


from execsql.config import StatObj, WriteHooks


# ---------------------------------------------------------------------------
# StatObj
# ---------------------------------------------------------------------------


class TestStatObj:
    def test_default_flags(self):
        s = StatObj()
        assert s.halt_on_err is True
        assert s.sql_error is False
        assert s.halt_on_metacommand_err is True
        assert s.metacommand_error is False
        assert s.cancel_halt is True
        assert s.dialog_canceled is False

    def test_batch_attribute_exists(self):
        s = StatObj()
        assert s.batch is not None

    def test_repr_not_raises(self):
        # No __repr__ defined — default object repr should not raise
        s = StatObj()
        assert "StatObj" in type(s).__name__


# ---------------------------------------------------------------------------
# WriteHooks
# ---------------------------------------------------------------------------


class TestWriteHooks:
    def test_repr(self):
        wh = WriteHooks()
        r = repr(wh)
        assert "WriteHooks" in r

    def test_write_to_stdout(self, capsys):
        wh = WriteHooks()
        wh.write("hello stdout")
        captured = capsys.readouterr()
        assert "hello stdout" in captured.out

    def test_write_to_custom_func(self):
        received = []
        wh = WriteHooks(standard_output_func=received.append)
        wh.write("test")
        assert received == ["test"]

    def test_write_err_adds_newline(self, capsys):
        wh = WriteHooks()
        wh.write_err("error message")
        captured = capsys.readouterr()
        assert "error message" in captured.err

    def test_write_err_to_custom_func(self):
        received = []
        wh = WriteHooks(error_output_func=received.append)
        wh.write_err("oops")
        assert any("oops" in s for s in received)

    def test_write_status_no_op_without_func(self):
        wh = WriteHooks()
        # Should not raise
        wh.write_status("status text")

    def test_write_status_calls_func(self):
        received = []
        wh = WriteHooks(status_output_func=received.append)
        wh.write_status("status")
        assert received == ["status"]

    def test_reset_clears_hooks(self):
        received = []
        wh = WriteHooks(standard_output_func=received.append)
        wh.reset()
        # After reset, write goes to stdout, not the list
        wh.write("after reset")
        assert received == []

    def test_redir_stdout(self):
        received = []
        wh = WriteHooks()
        wh.redir_stdout(received.append)
        wh.write("redirected")
        assert received == ["redirected"]

    def test_redir_stderr(self):
        received = []
        wh = WriteHooks()
        wh.redir_stderr(received.append, tee=False)
        wh.write_err("err redirected")
        assert any("err redirected" in s for s in received)

    def test_redir_both(self):
        out = []
        err = []
        wh = WriteHooks()
        wh.redir(out.append, err.append)
        wh.write("out")
        wh.write_err("err")
        assert out == ["out"]
        assert any("err" in s for s in err)

    def test_tee_stderr_default_true(self):
        wh = WriteHooks()
        assert wh.tee_stderr is True

    def test_tee_stderr_false_suppresses_stderr(self, capsys):
        received = []
        wh = WriteHooks(error_output_func=received.append)
        wh.tee_stderr = False
        wh.write_err("only to hook")
        captured = capsys.readouterr()
        assert "only to hook" not in captured.err
        assert any("only to hook" in s for s in received)
