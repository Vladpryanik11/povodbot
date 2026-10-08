import re
from dataclasses import dataclass
from uuid import UUID

from aiogram.types import InlineKeyboardMarkup
from aiogram.types import User as TelegramUser

from src.bot.keyboards.main_menu import consent_prompt, main_menu
from src.models.identity import ConsentSource, ConsentType
from src.services.consents.service import ConsentService, StaleConsentRevision
from src.services.directions.service import DirectionService
from src.services.users.service import UserService


@dataclass(frozen=True)
class ConsentTexts:
    # Owner-approved legal texts are pending in the approved spec.
    # Configure explicit versions/texts when composing the production router.
    personal_data_text: str = (
        "Тестовый текст согласия: разрешаю обработку профиля Telegram для работы клуба «Повод». "
        "Перед коммерческим запуском текст должен быть утверждён."
    )
    marketing_text: str = (
        "Тестовый текст согласия: разрешаю рекламные сообщения клуба «Повод» в Telegram. "
        "Согласие добровольное; его можно отозвать в меню. "
        "Перед коммерческим запуском текст должен быть утверждён."
    )
    personal_data_version: str = "draft-v1"
    marketing_version: str = "draft-v1"

    def __post_init__(self) -> None:
        for version in (self.personal_data_version, self.marketing_version):
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,16}", version):
                raise ValueError("Bot consent versions must be 1 to 16 ASCII characters")
        if not self.personal_data_text.strip() or not self.marketing_text.strip():
            raise ValueError("Consent prompt texts cannot be empty")


@dataclass(frozen=True)
class BotResponse:
    text: str
    keyboard: InlineKeyboardMarkup


class StartHandler:
    def __init__(
        self,
        users: UserService,
        consents: ConsentService,
        directions: DirectionService,
        texts: ConsentTexts,
    ):
        self.users = users
        self.consents = consents
        self.directions = directions
        self.texts = texts

    async def prompt(self, user_id: UUID, consent_type: ConsentType) -> BotResponse:
        if consent_type == ConsentType.PERSONAL_DATA:
            text = self.texts.personal_data_text
            version = self.texts.personal_data_version
        else:
            text = self.texts.marketing_text
            version = self.texts.marketing_version
        latest = await self.consents.latest(user_id, consent_type)
        sequence = latest.sequence if latest else 0
        return BotResponse(
            f"{text}\nВерсия: {version}", consent_prompt(consent_type, version, sequence)
        )

    async def start(self, sender: TelegramUser, start_param: str | None) -> BotResponse:
        user = await self.users.upsert_telegram_user(
            sender.id, sender.first_name, sender.last_name, sender.username, start_param
        )
        if not await self.consents.is_active(user.id, ConsentType.PERSONAL_DATA):
            return await self.prompt(user.id, ConsentType.PERSONAL_DATA)
        if await self.consents.latest(user.id, ConsentType.MARKETING) is None:
            return await self.prompt(user.id, ConsentType.MARKETING)
        return await self.menu(user.id)

    async def menu(self, user_id: UUID) -> BotResponse:
        active = await self.consents.is_active(user_id, ConsentType.MARKETING)
        latest = await self.consents.latest(user_id, ConsentType.MARKETING)
        return BotResponse(
            "Добро пожаловать в «Повод»! Выберите направление.",
            main_menu(
                await self.directions.list_active(),
                active,
                self.texts.marketing_version,
                latest.sequence if latest else 0,
            ),
        )

    async def consent(self, sender: TelegramUser, data: str) -> BotResponse:
        user = await self.users.upsert_telegram_user(
            sender.id, sender.first_name, sender.last_name, sender.username, None
        )
        personal_active = await self.consents.is_active(user.id, ConsentType.PERSONAL_DATA)
        parts = data.split(":")
        if len(parts) not in {4, 5} or parts[1] not in {t.value for t in ConsentType}:
            return await self.start(sender, None)
        consent_type = ConsentType(parts[1])
        action, version = parts[2:4]
        current_version = (
            self.texts.personal_data_version
            if consent_type == ConsentType.PERSONAL_DATA
            else self.texts.marketing_version
        )
        # Revocation is unconditional; old text versions must never prevent opt-out.
        if consent_type == ConsentType.MARKETING and action in {"revoke", "skip"}:
            await self.consents.revoke(user.id, consent_type, ConsentSource.TELEGRAM)
            if not personal_active:
                return await self.prompt(user.id, ConsentType.PERSONAL_DATA)
            return await self.menu(user.id)
        if consent_type == ConsentType.MARKETING and not personal_active:
            return await self.prompt(user.id, ConsentType.PERSONAL_DATA)
        if version != current_version or action != "grant":
            return await self.prompt(user.id, consent_type)
        if (
            len(parts) != 5
            or not re.fullmatch(r"[0-9]{1,19}", parts[4])
            or int(parts[4]) > 2**63 - 1
        ):
            return await self.prompt(user.id, consent_type)
        try:
            await self.consents.record(
                user.id,
                consent_type,
                version,
                ConsentSource.TELEGRAM,
                expected_sequence=int(parts[4]),
            )
        except StaleConsentRevision:
            response = await self.prompt(user.id, consent_type)
            return BotResponse(
                "Кнопка согласия устарела. Проверьте текст и используйте новую кнопку.\n"
                + response.text,
                response.keyboard,
            )
        if consent_type == ConsentType.PERSONAL_DATA:
            return await self.prompt(user.id, ConsentType.MARKETING)
        return await self.menu(user.id)
