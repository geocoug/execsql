"""Additional tests for execsql.utils.timer — TimerHandler alarm_handler."""

from __future__ import annotations

import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from execsql.exceptions import ExecSqlTimeoutError
from execsql.utils.timer import TimerHandler


@pytest.mark.skipif(sys.platform == "win32", reason="signal.setitimer not available on Windows")
class TestTimerHandlerAlarm:
    def test_alarm_handler_raises_on_timeout(self):
        th = TimerHandler(maxtime=0.0)
        th.start_time = time.time() - 1.0  # Expired 1 second ago

        with patch("signal.setitimer"), pytest.raises(ExecSqlTimeoutError):
            th.alarm_handler(14, None)

    def test_alarm_handler_progress_bar_when_not_expired(self):
        import execsql.state as _state

        th = TimerHandler(maxtime=100.0)
        th.start_time = time.time()  # Just started

        mock_output = MagicMock()
        _state.output = mock_output

        th.alarm_handler(14, None)
        mock_output.write.assert_called_once()
        written = mock_output.write.call_args[0][0]
        assert "|" in written  # Progress bar contains pipes
