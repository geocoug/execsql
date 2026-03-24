"""Tests for timer utilities in execsql.utils.timer."""

from __future__ import annotations

import time


from execsql.utils.timer import Timer, TimerHandler


# ---------------------------------------------------------------------------
# Timer
# ---------------------------------------------------------------------------


class TestTimer:
    def test_repr(self):
        t = Timer()
        assert repr(t) == "Timer()"

    def test_initial_state(self):
        t = Timer()
        assert t.running is False
        assert t.start_time == 0.0
        assert t.elapsed_time == 0.0

    def test_start_sets_running(self):
        t = Timer()
        t.start()
        assert t.running is True

    def test_elapsed_while_running_is_positive(self):
        t = Timer()
        t.start()
        e = t.elapsed()
        assert e >= 0.0

    def test_elapsed_increases_while_running(self):
        t = Timer()
        t.start()
        e1 = t.elapsed()
        time.sleep(0.01)
        e2 = t.elapsed()
        assert e2 >= e1

    def test_stop_sets_not_running(self):
        t = Timer()
        t.start()
        t.stop()
        assert t.running is False

    def test_elapsed_after_stop_is_fixed(self):
        t = Timer()
        t.start()
        time.sleep(0.01)
        t.stop()
        e1 = t.elapsed()
        time.sleep(0.01)
        e2 = t.elapsed()
        assert e1 == e2

    def test_stop_captures_elapsed_time(self):
        t = Timer()
        t.start()
        time.sleep(0.02)
        t.stop()
        assert t.elapsed_time >= 0.01

    def test_elapsed_when_not_running_returns_elapsed_time(self):
        t = Timer()
        t.start()
        time.sleep(0.01)
        t.stop()
        stored = t.elapsed_time
        assert t.elapsed() == stored

    def test_restart(self):
        t = Timer()
        t.start()
        time.sleep(0.01)
        t.stop()
        t.elapsed()
        t.start()
        time.sleep(0.01)
        t.stop()
        e2 = t.elapsed()
        # Both runs should be roughly equal (both ~0.01s)
        assert e2 >= 0.005


# ---------------------------------------------------------------------------
# TimerHandler — construction only (signal-based methods need OS support)
# ---------------------------------------------------------------------------


class TestTimerHandler:
    def test_init_stores_maxtime(self):
        th = TimerHandler(maxtime=30.0)
        assert th.maxtime == 30.0

    def test_init_records_start_time(self):
        before = time.time()
        th = TimerHandler(maxtime=5.0)
        after = time.time()
        assert before <= th.start_time <= after

    def test_fractional_maxtime(self):
        th = TimerHandler(maxtime=0.5)
        assert th.maxtime == 0.5
