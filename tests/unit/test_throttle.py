from src.workers.throttle import Throttle


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


async def test_throttle_spaces_calls() -> None:
    clock = FakeClock()
    throttle = Throttle(25, clock=clock, sleep=clock.sleep)

    for _ in range(25):
        await throttle.wait()
    assert sum(clock.slept) <= 1.0

    await throttle.wait()
    assert sum(clock.slept) >= 1.0


async def test_throttle_does_not_sleep_when_calls_are_slow() -> None:
    clock = FakeClock()
    throttle = Throttle(2, clock=clock, sleep=clock.sleep)

    for _ in range(5):
        await throttle.wait()
        clock.now += 0.6

    assert clock.slept == []
