from datetime import UTC, datetime, timedelta, timezone

import pytest

from src.services.campaigns.launch import is_quiet, next_morning

MSK = timezone(timedelta(hours=3))


@pytest.mark.parametrize(
    ("hour", "minute", "quiet"),
    [(21, 59, False), (22, 0, True), (9, 59, True), (10, 0, False), (3, 0, True), (15, 0, False)],
)
def test_quiet_hours_in_moscow_time(hour: int, minute: int, quiet: bool) -> None:
    assert is_quiet(datetime(2026, 10, 12, hour, minute, tzinfo=MSK)) is quiet


def test_quiet_hours_convert_other_zones() -> None:
    assert is_quiet(datetime.fromisoformat("2026-10-11T19:00:00Z")) is True
    assert is_quiet(datetime.fromisoformat("2026-10-12T09:30:00+05:00")) is True
    assert is_quiet(datetime.fromisoformat("2026-10-12T07:00:00Z")) is False


def test_next_morning_is_ten_moscow_time_in_utc() -> None:
    late = next_morning(datetime(2026, 10, 12, 23, 30, tzinfo=MSK))
    early = next_morning(datetime(2026, 10, 12, 3, 0, tzinfo=MSK))
    assert late == datetime(2026, 10, 13, 7, 0, tzinfo=UTC)
    assert early == datetime(2026, 10, 12, 7, 0, tzinfo=UTC)
    assert late.tzinfo == UTC
