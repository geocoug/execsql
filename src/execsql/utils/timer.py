from __future__ import annotations

"""
Timer and alarm utilities for execsql.

Provides:

- :class:`Timer` — records script elapsed time and exposes it as the
  ``$TIMER`` substitution variable; supports named checkpoint timers.
- Alarm/timeout support via :class:`~execsql.exceptions.ExecSqlTimeoutError`
  for the ``TIMEOUT`` metacommand (POSIX ``SIGALRM``-based on Unix,
  thread-based on Windows).
"""

import signal
import time

from execsql.exceptions import ExecSqlTimeoutError

__all__ = ["Timer", "TimerHandler"]


class TimerHandler:
    def __init__(self, maxtime: float) -> None:
        # maxtime should be in seconds, may be floating-point.
        self.maxtime = maxtime
        self.start_time = time.time()

    def alarm_handler(self, sig: int, stackframe: object) -> None:
        import execsql.state as _state

        elapsed_time = time.time() - self.start_time
        if elapsed_time > self.maxtime:
            signal.setitimer(signal.ITIMER_REAL, 0)
            raise ExecSqlTimeoutError
        else:
            time_left = self.maxtime - elapsed_time
            barlength = 30
            bar_left = int(round(barlength * time_left / self.maxtime, 0))
            _state.output.write(
                "{:8.1f}  |{}{}|\r".format(time_left, "+" * bar_left, "-" * (barlength - bar_left)),
            )


class Timer:
    def __repr__(self) -> str:
        return "Timer()"

    def __init__(self) -> None:
        self.running = False
        self.start_time = 0.0
        self.elapsed_time = 0.0

    def start(self) -> None:
        self.running = True
        self.start_time = time.time()

    def stop(self) -> None:
        self.elapsed_time = time.time() - self.start_time
        self.running = False

    def elapsed(self) -> float:
        if self.running:
            return time.time() - self.start_time
        else:
            return self.elapsed_time
