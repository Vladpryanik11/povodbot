from dataclasses import dataclass


@dataclass(frozen=True)
class SupportHandler:
    contact_text: str = "Напишите администратору клуба «Повод» — мы поможем разобраться с заказом."

    def answer(self) -> str:
        return self.contact_text
