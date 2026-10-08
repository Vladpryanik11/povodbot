import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.models.directions import Direction
from src.repositories.directions import DirectionRepository


@dataclass(frozen=True)
class CreateDirectionCommand:
    slug: str
    name: str
    description: str | None = None
    sort_order: int = 0
    active: bool = True


@dataclass(frozen=True)
class DirectionDTO:
    id: UUID
    slug: str
    name: str
    description: str | None
    sort_order: int
    active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, direction: Direction) -> "DirectionDTO":
        return cls(
            direction.id,
            direction.slug,
            direction.name,
            direction.description,
            direction.sort_order,
            direction.active,
            direction.created_at,
            direction.updated_at,
        )


class DirectionService:
    def __init__(self, repository: DirectionRepository):
        self.repository = repository

    async def create(self, command: CreateDirectionCommand) -> DirectionDTO:
        if len(command.slug) > 64 or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", command.slug):
            raise ValueError("Direction slug must be lowercase words separated by hyphens")
        if not command.name.strip() or len(command.name) > 256:
            raise ValueError("Direction name must contain 1 to 256 characters")
        return DirectionDTO.from_model(
            await self.repository.create(
                command.slug, command.name, command.description, command.sort_order, command.active
            )
        )

    async def list_active(self) -> list[DirectionDTO]:
        return [DirectionDTO.from_model(d) for d in await self.repository.list_active()]

    async def set_active(self, direction_id: UUID, active: bool) -> DirectionDTO:
        return DirectionDTO.from_model(await self.repository.set_active(direction_id, active))
