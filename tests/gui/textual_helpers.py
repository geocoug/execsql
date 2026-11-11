"""Coordinate Textual test drivers, worker releases, and dialog completion."""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import suppress


def wait_for_release(event: threading.Event, timeout: float = 20) -> None:
    """Wait for a synthetic driver release without holding a condition lock.

    Injecting SystemExit into Event.wait() can block the UI's Event.set()
    under the Windows coverage tracer. Polling leaves no condition lock in
    the interrupt path, while retaining a deadline for a broken test driver.
    """
    deadline = time.monotonic() + timeout
    while not event.is_set():
        if time.monotonic() >= deadline:
            raise AssertionError("Timed out waiting for the worker release gate")
        time.sleep(0.01)


async def finish_dialog(pilot, action):
    """Drive a terminal gesture until the real app exits, propagating failures."""
    gesture = asyncio.create_task(action)

    async def wait():
        while not pilot.app._exit:
            if gesture.done():
                assert gesture.result() is not False, "Gesture missed its target"
            await asyncio.sleep(0.01)

    try:
        await asyncio.wait_for(wait(), timeout=10)
        if gesture.done():
            assert gesture.result() is not False, "Gesture missed its target"
    finally:
        gesture.cancel()
        with suppress(asyncio.CancelledError):
            await gesture
