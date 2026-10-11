from dataclasses import dataclass

from src.bot import copy


@dataclass(frozen=True)
class SupportHandler:
    contact: str = ""

    def answer(self) -> str:
        contact = self.contact.strip()
        if contact:
            return copy.SUPPORT_WITH_CONTACT.format(contact=contact)
        return copy.SUPPORT_NO_CONTACT
