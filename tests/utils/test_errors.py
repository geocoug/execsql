"""Tests for error-handling utilities in execsql.utils.errors."""

from __future__ import annotations

import os
import tempfile


import execsql.state as _state
from execsql.utils.errors import exception_desc, exception_info, file_size_date, write_warning


# ---------------------------------------------------------------------------
# file_size_date
# ---------------------------------------------------------------------------


class TestFileSizeDate:
    def test_returns_two_elements(self):
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"hello")
            name = tf.name
        try:
            result = file_size_date(name)
            assert len(result) == 2
        finally:
            os.unlink(name)

    def test_size_matches_written_content(self):
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"abcde")
            name = tf.name
        try:
            size, _ = file_size_date(name)
            assert size == 5
        finally:
            os.unlink(name)

    def test_date_format(self):
        import re

        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"x")
            name = tf.name
        try:
            _, date_str = file_size_date(name)
            # Expected format: YYYY-MM-DD HH:MM
            assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", date_str)
        finally:
            os.unlink(name)

    def test_empty_file_size_zero(self):
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            name = tf.name
        try:
            size, _ = file_size_date(name)
            assert size == 0
        finally:
            os.unlink(name)


# ---------------------------------------------------------------------------
# exception_info / exception_desc
# ---------------------------------------------------------------------------


class TestExceptionInfo:
    def test_returns_five_elements(self):
        try:
            raise ValueError("test error")
        except Exception:
            info = exception_info()
        assert len(info) == 5

    def test_first_element_is_exception_type_name(self):
        try:
            raise ValueError("test error")
        except Exception:
            info = exception_info()
        assert info[0] == "ValueError"

    def test_second_element_is_message(self):
        try:
            raise ValueError("my message")
        except Exception:
            info = exception_info()
        assert "my message" in info[1]

    def test_runtime_error_type(self):
        try:
            raise RuntimeError("boom")
        except Exception:
            info = exception_info()
        assert info[0] == "RuntimeError"

    def test_exception_desc_is_string(self):
        try:
            raise TypeError("bad type")
        except Exception:
            desc = exception_desc()
        assert isinstance(desc, str)

    def test_exception_desc_contains_type_name(self):
        try:
            raise TypeError("bad type")
        except Exception:
            desc = exception_desc()
        assert "TypeError" in desc

    def test_exception_desc_contains_message(self):
        try:
            raise TypeError("bad type")
        except Exception:
            desc = exception_desc()
        assert "bad type" in desc

    def test_exception_with_no_message(self):
        try:
            raise RuntimeError()
        except Exception:
            info = exception_info()
        # Should not raise; message may be empty string.
        assert isinstance(info[1], str)


# ---------------------------------------------------------------------------
# write_warning — null-safety guards
# ---------------------------------------------------------------------------


class TestWriteWarning:
    """Verify write_warning tolerates None state globals."""

    def test_no_error_when_exec_log_is_none(self):
        """write_warning must not raise when exec_log is None."""
        assert _state.exec_log is None
        write_warning("some warning")  # should not raise

    def test_no_error_when_conf_is_none(self):
        """write_warning must not raise when conf is None."""
        _state.conf = None
        write_warning("another warning")

    def test_no_error_when_output_is_none(self):
        """write_warning must not raise when output is None."""
        assert _state.output is None
        write_warning("yet another warning")

    def test_logs_when_exec_log_set(self):
        """write_warning calls log_status_warning when exec_log is set."""
        warnings = []

        class FakeLog:
            def log_status_warning(self, msg):
                warnings.append(msg)

        _state.exec_log = FakeLog()
        write_warning("test warning")
        assert warnings == ["test warning"]

    def test_writes_output_when_configured(self, minimal_conf):
        """write_warning writes to output when write_warnings is True."""
        written = []

        class FakeOutput:
            def write_err(self, msg):
                written.append(msg)

        minimal_conf.write_warnings = True
        _state.output = FakeOutput()
        write_warning("test warning")
        assert len(written) == 1
        assert "test warning" in written[0]


# ---------------------------------------------------------------------------
# exception_info — custom exception attributes
# ---------------------------------------------------------------------------


class TestExceptionInfoAttributes:
    def test_exception_with_message_attribute(self):
        """exception_info extracts .message from non-string exceptions."""

        class CustomExc(Exception):
            def __init__(self):
                self.message = "from message attr"

        try:
            raise CustomExc()
        except Exception:
            info = exception_info()
        assert "from message attr" in info[1]

    def test_exception_with_value_attribute(self):
        """exception_info extracts .value when .message is absent."""

        class CustomExc(Exception):
            def __init__(self):
                self.value = "from value attr"

        try:
            raise CustomExc()
        except Exception:
            info = exception_info()
        assert "from value attr" in info[1]

    def test_exception_str_fallback(self):
        """exception_info falls back to str() when no .message/.value."""
        try:
            raise RuntimeError("str fallback msg")
        except Exception:
            info = exception_info()
        assert "str fallback msg" in info[1]


# ---------------------------------------------------------------------------
# exit_now — logging paths
# ---------------------------------------------------------------------------


class TestExitNow:
    def setup_method(self):
        _state.reset()

    def teardown_method(self):
        _state.reset()

    def test_exit_now_exits_with_status(self):
        from unittest.mock import patch
        from execsql.utils.errors import exit_now

        with patch("execsql.utils.errors.sys.exit") as mock_exit, patch("execsql.utils.fileio.filewriter_end"):
            exit_now(0, None)
            mock_exit.assert_called_once_with(0)

    def test_exit_now_logs_error_message(self):
        from unittest.mock import patch, MagicMock
        from execsql.utils.errors import exit_now

        fake_log = MagicMock()
        _state.exec_log = fake_log

        with patch("execsql.utils.errors.sys.exit"), patch("execsql.utils.fileio.filewriter_end"):
            exit_now(1, None, logmsg="custom error")
            fake_log.log_exit_error.assert_called_once_with("custom error")

    def test_exit_now_logs_errinfo_message(self):
        from unittest.mock import patch, MagicMock
        from execsql.utils.errors import exit_now
        from execsql.exceptions import ErrInfo

        fake_log = MagicMock()
        _state.exec_log = fake_log
        _state.output = MagicMock()  # ErrInfo.write() needs output

        errinfo = ErrInfo("error", other_msg="boom")
        with patch("execsql.utils.errors.sys.exit"), patch("execsql.utils.fileio.filewriter_end"):
            exit_now(1, errinfo)
            fake_log.log_exit_error.assert_called_once()


# ---------------------------------------------------------------------------
# fatal_error
# ---------------------------------------------------------------------------


class TestFatalError:
    def setup_method(self):
        _state.reset()

    def teardown_method(self):
        _state.reset()

    def test_fatal_error_calls_exit_now(self):
        from unittest.mock import patch
        from execsql.utils.errors import fatal_error

        _state.output = type("FakeOutput", (), {"write_err": lambda self, m: None})()
        with patch("execsql.utils.errors.sys.exit") as mock_exit, patch("execsql.utils.fileio.filewriter_end"):
            fatal_error("test error")
            mock_exit.assert_called_once_with(1)
