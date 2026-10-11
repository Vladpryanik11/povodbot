"""Keeps broadcast sends under Telegram's per-second limit."""

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable


class Throttle:
    """At most `rate` calls in any one-second window; the next one waits for the window to slide."""

    def __init__(
        self,
        rate: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if rate <= 0:
            raise ValueError("Rate must be positive")
        self.clock = clock
        self.sleep = sleep
        self._recent: deque[float] = deque(maxlen=rate)

    async def wait(self) -> None:
        if len(self._recent) == self._recent.maxlen:
            pause = self._recent[0] + 1.0 - self.clock()
            if pause > 0:
                await self.sleep(pause)
        self._recent.append(self.clock())
