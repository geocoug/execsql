"""Tests for error-handling utilities in execsql.utils.errors."""

from __future__ import annotations

import os
import tempfile


import execsql.state as _state
from execsql.utils.errors import as_none, chainfuncs, exception_desc, exception_info, file_size_date, write_warning


# ---------------------------------------------------------------------------
# as_none
# ---------------------------------------------------------------------------


class TestAsNone:
    def test_empty_string_returns_none(self):
        assert as_none("") is None

    def test_non_empty_string_unchanged(self):
        assert as_none("hello") == "hello"

    def test_zero_int_returns_none(self):
        assert as_none(0) is None

    def test_nonzero_int_unchanged(self):
        assert as_none(1) == 1
        assert as_none(-1) == -1

    def test_none_returned_as_is(self):
        # None is not a str or int, so it passes through unchanged.
        assert as_none(None) is None

    def test_list_returned_as_is(self):
        lst = [1, 2, 3]
        assert as_none(lst) is lst

    def test_float_zero_returned_as_is(self):
        # Only int 0 is converted; float 0.0 passes through.
        result = as_none(0.0)
        assert result == 0.0

    def test_whitespace_string_unchanged(self):
        # Only the empty string is converted, not whitespace strings.
        assert as_none("   ") == "   "


# ---------------------------------------------------------------------------
# chainfuncs
# ---------------------------------------------------------------------------


class TestChainFuncs:
    def test_calls_each_function(self):
        calls = []
        chainfuncs(
            lambda: calls.append(1),
            lambda: calls.append(2),
            lambda: calls.append(3),
        )()
        assert calls == [1, 2, 3]

    def test_single_function(self):
        called = []
        f = chainfuncs(lambda: called.append(True))
        f()
        assert called == [True]

    def test_returns_callable(self):
        f = chainfuncs(lambda: None)
        assert callable(f)

    def test_no_functions(self):
        f = chainfuncs()
        f()  # should not raise

    def test_called_multiple_times(self):
        count = []
        f = chainfuncs(lambda: count.append(1))
        f()
        f()
        assert len(count) == 2

    def test_functions_called_in_order(self):
        order = []
        f = chainfuncs(lambda: order.append("first"), lambda: order.append("second"))
        f()
        assert order == ["first", "second"]


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

    def setup_method(self):
        _state.reset()

    def teardown_method(self):
        _state.reset()

    def test_no_error_when_exec_log_is_none(self):
        """write_warning must not raise when exec_log is None."""
        assert _state.exec_log is None
        write_warning("some warning")  # should not raise

    def test_no_error_when_conf_is_none(self):
        """write_warning must not raise when conf is None."""
        assert _state.conf is None
        write_warning("another warning")

    def test_no_error_when_output_is_none(self):
        """write_warning must not raise when output is None."""
        assert _state.output is None
        write_warning("yet another warning")
