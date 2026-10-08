from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

import structlog

from src.core.config import Settings
from src.core.logging import configure_logging

_metrics: Counter[str] = Counter()
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def configure_observability(settings: Settings) -> None:
    configure_logging(settings)


def increment(name: str, value: int = 1) -> None:
    if not name or value < 0:
        raise ValueError("Metric name and value are invalid")
    _metrics[name] += value


def snapshot_metrics() -> dict[str, int]:
    return dict(_metrics)


@contextmanager
def correlation_scope(value: str | None = None) -> Iterator[str]:
    correlation_id = value or uuid4().hex
    token = _correlation_id.set(correlation_id)
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
    try:
        yield correlation_id
    finally:
        structlog.contextvars.unbind_contextvars("correlation_id")
        _correlation_id.reset(token)
