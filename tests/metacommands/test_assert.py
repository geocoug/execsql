"""Unit tests for the ASSERT metacommand handler (x_assert).

Covers:
- True condition passes silently
- False condition raises ErrInfo with user-supplied message
- False condition with no message raises ErrInfo with default message
- Single-quoted and double-quoted messages are stripped correctly
- ErrInfo is raised for unrecognized conditions (xcmd_test raises)
- exec_log.log_user_msg is called on success
- Dispatch regex correctly matches various ASSERT syntaxes
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.metacommands.control import x_assert


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_exec_log() -> MagicMock:
    """Return a mock exec_log with a no-op log_user_msg."""
    log = MagicMock()
    log.log_user_msg = MagicMock()
    return log


# ---------------------------------------------------------------------------
# x_assert unit tests
# ---------------------------------------------------------------------------


class TestXAssertPassesOnTrueCondition:
    """x_assert returns None and logs when the condition is True."""

    def test_true_condition_returns_none(self) -> None:
        mock_log = _make_exec_log()
        with (
            patch.object(_state, "xcmd_test", return_value=True),
            patch.object(_state, "exec_log", mock_log),
        ):
            result = x_assert(condtest="ROWCOUNT > 0", message=None, metacommandline="ASSERT ROWCOUNT > 0")
        assert result is None

    def test_true_condition_logs_pass(self) -> None:
        mock_log = _make_exec_log()
        with (
            patch.object(_state, "xcmd_test", return_value=True),
            patch.object(_state, "exec_log", mock_log),
        ):
            x_assert(condtest="TABLE_EXISTS my_table", message=None, metacommandline="ASSERT TABLE_EXISTS my_table")
        mock_log.log_user_msg.assert_called_once()
        call_msg: str = mock_log.log_user_msg.call_args[0][0]
        assert "ASSERT passed" in call_msg
        assert "TABLE_EXISTS my_table" in call_msg


class TestXAssertRaisesOnFalseCondition:
    """x_assert raises ErrInfo when the condition is False."""

    def test_false_condition_raises_errinfo(self) -> None:
        mock_log = _make_exec_log()
        with (
            patch.object(_state, "xcmd_test", return_value=False),
            patch.object(_state, "exec_log", mock_log),
            pytest.raises(ErrInfo) as exc_info,
        ):
            x_assert(condtest="ROWCOUNT > 0", message=None, metacommandline="ASSERT ROWCOUNT > 0")
        assert exc_info.value.type == "assert"

    def test_false_condition_eval_err_says_assertion_failed(self) -> None:
        mock_log = _make_exec_log()
        with (
            patch.object(_state, "xcmd_test", return_value=False),
            patch.object(_state, "exec_log", mock_log),
            pytest.raises(ErrInfo) as exc_info,
        ):
            x_assert(condtest="ROWCOUNT > 0", message='"expected rows"', metacommandline="ASSERT ROWCOUNT > 0")
        err_msg = exc_info.value.eval_err()
        assert err_msg.startswith("**** Assertion failed.")
        assert "expected rows" in err_msg

    def test_false_condition_with_double_quoted_message(self) -> None:
        mock_log = _make_exec_log()
        with (
            patch.object(_state, "xcmd_test", return_value=False),
            patch.object(_state, "exec_log", mock_log),
            pytest.raises(ErrInfo) as exc_info,
        ):
            x_assert(
                condtest="ROWCOUNT > 0",
                message='"table must not be empty"',
                metacommandline='ASSERT ROWCOUNT > 0 "table must not be empty"',
            )
        assert "table must not be empty" in str(exc_info.value)

    def test_false_condition_with_single_quoted_message(self) -> None:
        mock_log = _make_exec_log()
        with (
            patch.object(_state, "xcmd_test", return_value=False),
            patch.object(_state, "exec_log", mock_log),
            pytest.raises(ErrInfo) as exc_info,
        ):
            x_assert(
                condtest="$VAR = 'expected'",
                message="'wrong value'",
                metacommandline="ASSERT $VAR = 'expected' 'wrong value'",
            )
        assert "wrong value" in str(exc_info.value)
        # The message should NOT contain the surrounding quotes
        assert str(exc_info.value) == "wrong value"

    def test_false_condition_no_message_uses_default(self) -> None:
        condition = "TABLE_EXISTS missing_table"
        mock_log = _make_exec_log()
        with (
            patch.object(_state, "xcmd_test", return_value=False),
            patch.object(_state, "exec_log", mock_log),
            pytest.raises(ErrInfo) as exc_info,
        ):
            x_assert(condtest=condition, message=None, metacommandline=f"ASSERT {condition}")
        default_msg = str(exc_info.value)
        assert "Assertion failed" in default_msg
        assert condition in default_msg

    def test_false_condition_does_not_log_pass(self) -> None:
        mock_log = _make_exec_log()
        with (
            patch.object(_state, "xcmd_test", return_value=False),
            patch.object(_state, "exec_log", mock_log),
            pytest.raises(ErrInfo),
        ):
            x_assert(condtest="ROWCOUNT > 0", message=None, metacommandline="ASSERT ROWCOUNT > 0")
        mock_log.log_user_msg.assert_not_called()


class TestXAssertUnrecognizedCondition:
    """x_assert propagates ErrInfo raised by xcmd_test for unknown conditions."""

    def test_unrecognized_condition_raises_errinfo(self) -> None:
        mock_log = _make_exec_log()
        with (
            patch.object(_state, "xcmd_test", side_effect=ErrInfo(type="cmd", other_msg="Unrecognized conditional")),
            patch.object(_state, "exec_log", mock_log),
            pytest.raises(ErrInfo) as exc_info,
        ):
            x_assert(condtest="BLARG_CONDITION", message=None, metacommandline="ASSERT BLARG_CONDITION")
        assert "Unrecognized conditional" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Dispatch regex tests
# ---------------------------------------------------------------------------


class TestAssertDispatchRegex:
    """The ASSERT entries in the dispatch table match expected syntax."""

    @pytest.fixture(autouse=True)
    def _load_dispatch(self) -> None:
        from execsql.metacommands import DISPATCH_TABLE

        self.dt = DISPATCH_TABLE

    def _match(self, line: str) -> dict | None:
        """Return groupdict if any ASSERT entry matches *line*, else None."""
        import re

        for mc in self.dt:
            if not mc.description or "ASSERT" not in mc.description:
                continue
            m = re.match(mc.rx.pattern, line.strip(), re.IGNORECASE)
            if m:
                return m.groupdict()
        return None

    def test_assert_table_exists_no_message(self) -> None:
        gd = self._match("ASSERT TABLE_EXISTS foo")
        assert gd is not None
        assert "TABLE_EXISTS foo" in gd["condtest"]

    def test_assert_rowcount_with_double_quoted_message(self) -> None:
        gd = self._match('ASSERT ROWCOUNT > 0 "rows expected"')
        assert gd is not None
        assert gd["message"] == '"rows expected"'

    def test_assert_var_comparison_with_single_quoted_message(self) -> None:
        gd = self._match("ASSERT $x = '1' 'wrong'")
        assert gd is not None
        assert gd["message"] == "'wrong'"

    def test_assert_no_message_returns_no_message_group(self) -> None:
        gd = self._match("ASSERT ROWCOUNT > 0")
        assert gd is not None
        # No message group in the no-message variant
        assert gd.get("message") is None

    def test_assert_run_when_false_is_false(self) -> None:
        """ASSERT must NOT run inside a False IF block."""
        for mc in self.dt:
            if mc.description and "ASSERT" in mc.description:
                assert mc.run_when_false is False, f"Expected run_when_false=False for {mc}"
