from dataclasses import dataclass

from aiogram.types import InlineKeyboardMarkup
from aiogram.types import User as TelegramUser

from src.bot import copy
from src.bot.keyboards.main_menu import main_menu
from src.services.analytics.attribution import AttributionService, FunnelEventName
from src.services.users.service import UserService


@dataclass(frozen=True)
class BotResponse:
    text: str
    keyboard: InlineKeyboardMarkup


def menu_response(
    first_name: str | None, miniapp_url: str = "", first_visit: bool = False
) -> BotResponse:
    name = (first_name or "").strip()
    if first_visit:
        template = copy.START_FIRST_NAMED if name else copy.START_FIRST_ANON
    else:
        template = copy.START_AGAIN_NAMED if name else copy.START_AGAIN_ANON
    return BotResponse(template.format(name=name), main_menu(miniapp_url))


class StartHandler:
    def __init__(
        self,
        users: UserService,
        attribution: AttributionService | None = None,
        miniapp_url: str = "",
    ):
        self.users = users
        self.attribution = attribution
        self.miniapp_url = miniapp_url

    async def start(self, sender: TelegramUser, start_param: str | None) -> BotResponse:
        existed = await self.users.repository.by_telegram_id(sender.id) is not None
        user = await self.users.upsert_telegram_user(
            sender.id, sender.first_name, sender.last_name, sender.username, start_param
        )
        if self.attribution is not None:
            await self.attribution.record_start(user.id, start_param, user.last_seen_at)
            await self.attribution.record_funnel_event(user.id, FunnelEventName.START)
        return self.menu(sender.first_name, first_visit=not existed)

    def menu(self, first_name: str | None, first_visit: bool = False) -> BotResponse:
        return menu_response(first_name, self.miniapp_url, first_visit)
