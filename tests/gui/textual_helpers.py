"""Wait for dialog completion without waiting on widgets being unmounted."""

from __future__ import annotations

import asyncio
from contextlib import suppress


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
