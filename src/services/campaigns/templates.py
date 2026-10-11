"""Broadcast templates: five ready ones from the migration, and the owner's own."""

from __future__ import annotations

import builtins
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.campaigns import Campaign, CampaignTemplate
from src.services.campaigns.content import CampaignFieldError, validate_body, validate_buttons

NAME_LIMIT = 128
EMPTY_NAME = "Назови шаблон"
IMAGE_KINDS = ("event", "upload", "none")
BUILTIN_LOCKED = "Готовый шаблон не меняется. Скопируй его в свои"
FIELDS = ("name", "body", "image_kind", "buttons")


class TemplateLocked(Exception):
    message = BUILTIN_LOCKED


class TemplateService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self) -> builtins.list[CampaignTemplate]:
        return list(
            await self.session.scalars(
                # Ready ones first (they share one timestamp, so by name); the owner's newest next.
                select(CampaignTemplate).order_by(
                    CampaignTemplate.is_builtin.desc(),
                    CampaignTemplate.updated_at.desc(),
                    CampaignTemplate.name,
                )
            )
        )

    async def create(self, actor_id: UUID | None, data: dict[str, Any]) -> CampaignTemplate:
        template = CampaignTemplate(
            name="", body="", image_kind="none", buttons=[], is_builtin=False, created_by=actor_id
        )
        self._apply(template, data)
        self.session.add(template)
        await self.session.flush()
        return template

    async def update(self, template_id: UUID, data: dict[str, Any]) -> CampaignTemplate:
        template = await self._own(template_id)
        self._apply(template, data)
        await self.session.flush()
        return template

    async def delete(self, template_id: UUID) -> None:
        await self.session.delete(await self._own(template_id))
        await self.session.flush()

    async def from_campaign(
        self, campaign_id: UUID, actor_id: UUID | None, name: str
    ) -> CampaignTemplate:
        campaign = await self.session.get(Campaign, campaign_id)
        if campaign is None:
            raise LookupError(campaign_id)
        return await self.create(
            actor_id,
            {
                "name": name,
                "body": campaign.body,
                "image_kind": campaign.image.get("kind", "none"),
                "buttons": campaign.buttons,
            },
        )

    async def _own(self, template_id: UUID) -> CampaignTemplate:
        template = await self.session.get(CampaignTemplate, template_id, with_for_update=True)
        if template is None:
            raise LookupError(template_id)
        if template.is_builtin:
            raise TemplateLocked()
        return template

    def _apply(self, template: CampaignTemplate, values: dict[str, Any]) -> None:
        unknown = set(values) - set(FIELDS)
        if unknown:
            raise ValueError(f"unknown template fields: {sorted(unknown)}")
        name = values.get("name", template.name)
        if not isinstance(name, str) or not name.strip():
            raise CampaignFieldError("name", EMPTY_NAME)
        image_kind = values.get("image_kind", template.image_kind)
        if image_kind not in IMAGE_KINDS:
            raise CampaignFieldError("image_kind", "Картинка не загрузилась. Попробуй ещё раз")
        # The evening is picked when the template is used, so an event button is fine here.
        buttons = validate_buttons(values.get("buttons", template.buttons), has_event=True)
        body = values.get("body", template.body)
        if not isinstance(body, str):
            raise CampaignFieldError("body", "Напиши текст рассылки")
        if body:
            validate_body(body, has_image=image_kind != "none")
        template.name = name.strip()[:NAME_LIMIT]
        template.image_kind = image_kind
        template.buttons = buttons
        template.body = body
