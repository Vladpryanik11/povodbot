from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True)
class Job:
    name: str
    payload: dict[str, str]
    id: UUID
    available_at: datetime


class InMemoryJobQueue:
    """Small local queue contract; production workers may replace it with Redis."""

    def __init__(self) -> None:
        self._jobs: list[Job] = []

    def enqueue(self, name: str, payload: dict[str, str]) -> Job:
        if not name or len(name) > 128:
            raise ValueError("Job name is invalid")
        job = Job(name, dict(payload), uuid4(), datetime.now(UTC))
        self._jobs.append(job)
        return job

    def drain(self, limit: int = 100) -> list[Job]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("Queue limit must be between 1 and 1000")
        result, self._jobs = self._jobs[:limit], self._jobs[limit:]
        return result
