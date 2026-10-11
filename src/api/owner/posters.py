"""Owner Mini App posters: upload a photo with its focus point, or move the focus alone."""

import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import File, Form, UploadFile
from pydantic import StrictFloat, StrictInt
from starlette.concurrency import run_in_threadpool

from src.api.owner.errors import OwnerApiError
from src.api.owner.events import Actor, Service, Session, audit, owner_errors
from src.api.owner.router import router
from src.api.owner.schemas import OwnerEventOut, OwnerIn, owner_event_out
from src.core.config import get_settings
from src.services.events.service import focus_point
from src.services.media.posters import MAX_BYTES, PosterError, store_poster

UPLOAD_BUSY = "Фото ещё загружается — подожди"

# One upload at a time per admin: decoding a photo is heavy. The locks live in this process,
# so with several uvicorn workers the limit is soft.
_upload_locks: dict[UUID, asyncio.Lock] = {}


class PosterFocusPatch(OwnerIn):
    focus_x: StrictFloat | StrictInt
    focus_y: StrictFloat | StrictInt


@router.post("/events/{event_id}/poster", response_model=OwnerEventOut)
async def upload_poster(
    event_id: UUID,
    file: Annotated[UploadFile, File()],
    focus_x: Annotated[float, Form()],
    focus_y: Annotated[float, Form()],
    actor: Actor,
    events: Service,
    session: Session,
) -> OwnerEventOut:
    lock = _upload_locks.setdefault(actor.id, asyncio.Lock())
    if lock.locked():
        raise OwnerApiError(429, {"message": UPLOAD_BUSY})
    async with lock:
        with owner_errors():
            # Cheap checks first: nothing is decoded or stored for a bad focus or a missing event.
            focus_point(focus_x, focus_y)
            await events.get(event_id)
        # One byte over the limit is enough for store_poster to answer 413.
        data = await file.read(MAX_BYTES + 1)
        try:
            stored = await run_in_threadpool(store_poster, data, get_settings().media_root)
        except PosterError as error:
            body = {"field": "poster", "message": error.message}
            raise OwnerApiError(error.status, body) from error
        with owner_errors():
            dto = await events.set_poster(
                event_id, stored.key, stored.width, stored.height, focus_x, focus_y
            )
    await audit(session, actor, "poster", dto.id, {"key": stored.key})
    return await owner_event_out(session, dto)


@router.patch("/events/{event_id}/poster-focus", response_model=OwnerEventOut)
async def move_poster_focus(
    event_id: UUID, body: PosterFocusPatch, actor: Actor, events: Service, session: Session
) -> OwnerEventOut:
    with owner_errors():
        dto = await events.set_poster_focus(event_id, body.focus_x, body.focus_y)
    await audit(session, actor, "poster_focus", dto.id)
    return await owner_event_out(session, dto)
