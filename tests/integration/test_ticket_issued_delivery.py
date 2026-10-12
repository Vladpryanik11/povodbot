from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, update

from src.models.events import Event
from src.models.outbox import Outbox
from src.models.tickets import Ticket, TicketStatus
from src.repositories.payments import PaymentRepository
from src.services.campaigns.telegram import RecipientBlocked, RetryAfter, SentMessage
from src.services.payments.dtos import (
    CreatePaymentResponse,
    PaymentWebhookDTO,
    ProviderOperationResult,
    ProviderPaymentStatus,
)
from src.services.payments.service import PaymentService
from src.services.reservations.service import ReservationItem
from src.workers.outbox import TicketIssuedOutboxWorker
from tests.commerce_fixtures import NOW, FixedClock, catalog, reservations


class Gateway:
    async def create_payment(self, request):
        return CreatePaymentResponse("ticket-payment", "https://pay", "NEW", request.amount_minor)

    async def get_status(self, provider_payment_id: str):
        return ProviderPaymentStatus(provider_payment_id, "CONFIRMED", 15000)

    async def cancel(self, provider_payment_id: str, amount_minor=None):
        return ProviderOperationResult(provider_payment_id, "CANCELED")

    async def refund(self, provider_payment_id: str, amount_minor: int, reason: str):
        return ProviderOperationResult(provider_payment_id, "REFUNDING")


class Sender:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls = []

    async def send(self, telegram_id, message):
        if self.error is not None:
            raise self.error
        self.calls.append((telegram_id, message))
        return SentMessage("1", None)


async def paid_order(pg_factory, quantity=1):
    async with pg_factory() as session, session.begin():
        event, user = await catalog(session)
        pending = await reservations(session).reserve(
            event.id, [ReservationItem(event.ticket_types[0].id, quantity)], user.id, NOW
        )
        payments = PaymentService(PaymentRepository(session), Gateway(), FixedClock(NOW))
        await payments.start(pending.order_id)
        await payments.apply_webhook(
            PaymentWebhookDTO(
                "ticket-payment", "CONFIRMED", 15000 * quantity, payload={"Status": "CONFIRMED"}
            )
        )
    return pending.order_id, event.id


async def job(pg_factory, order_id):
    async with pg_factory() as session:
        return await session.scalar(
            select(Outbox).where(Outbox.deduplication_key == f"ticket:issued:{order_id}")
        )


async def make_due(pg_factory, order_id):
    async with pg_factory() as session, session.begin():
        await session.execute(
            update(Outbox)
            .where(Outbox.deduplication_key == f"ticket:issued:{order_id}")
            .values(available_at=datetime.now(UTC) - timedelta(seconds=1))
        )


async def test_paid_order_enqueues_one_ticket_issued_job(pg_factory):
    order_id, _ = await paid_order(pg_factory)
    async with pg_factory() as session, session.begin():
        payments = PaymentService(PaymentRepository(session), Gateway(), FixedClock(NOW))
        await payments.apply_webhook(
            PaymentWebhookDTO("ticket-payment", "CONFIRMED", 15000, payload={"Status": "CONFIRMED"})
        )
        await payments.apply_webhook(
            PaymentWebhookDTO(
                "ticket-payment",
                "CONFIRMED",
                15000,
                event_id="second-delivery",
                payload={"Status": "CONFIRMED"},
            )
        )

    async with pg_factory() as session:
        jobs = list(
            await session.scalars(select(Outbox).where(Outbox.event_type == "ticket.issued"))
        )
    assert len(jobs) == 1
    assert jobs[0].deduplication_key == f"ticket:issued:{order_id}"
    assert jobs[0].payload == {"order_id": str(order_id)}


async def test_ticket_issued_message_names_event_and_time(pg_factory):
    order_id, event_id = await paid_order(pg_factory)
    sender = Sender()

    assert await TicketIssuedOutboxWorker(pg_factory, sender).process_pending() == 1

    assert len(sender.calls) == 1
    telegram_id, message = sender.calls[0]
    assert telegram_id == 100
    assert message.text.startswith("Оплата прошла, билет твой.")
    assert "Кино вечером" in message.text
    async with pg_factory() as session:
        event = await session.get(Event, event_id)
    local = event.starts_at.astimezone(ZoneInfo(event.timezone))
    assert f"{local:%d.%m.%Y} в {local:%H:%M}" in message.text
    assert (await job(pg_factory, order_id)).processed_at is not None


async def test_ticket_issued_message_counts_several_tickets(pg_factory):
    await paid_order(pg_factory, quantity=2)
    sender = Sender()

    await TicketIssuedOutboxWorker(pg_factory, sender).process_pending()

    assert sender.calls[0][1].text.startswith("Оплата прошла, билеты твои — 2 шт.")


async def test_ticket_issued_job_closes_when_recipient_blocked(pg_factory):
    order_id, _ = await paid_order(pg_factory)

    await TicketIssuedOutboxWorker(pg_factory, Sender(RecipientBlocked())).process_pending()

    assert (await job(pg_factory, order_id)).processed_at is not None
    async with pg_factory() as session:
        tickets = list(await session.scalars(select(Ticket).where(Ticket.order_id == order_id)))
    assert [ticket.status for ticket in tickets] == [TicketStatus.ISSUED]


async def test_ticket_issued_job_waits_on_retry_after(pg_factory):
    order_id, _ = await paid_order(pg_factory)
    before = datetime.now(UTC)

    await TicketIssuedOutboxWorker(pg_factory, Sender(RetryAfter(30))).process_pending()

    waiting = await job(pg_factory, order_id)
    assert waiting.processed_at is None
    assert waiting.available_at >= before + timedelta(seconds=30)


async def test_ticket_issued_gives_up_after_max_attempts(pg_factory):
    order_id, _ = await paid_order(pg_factory)
    worker = TicketIssuedOutboxWorker(pg_factory, Sender(RuntimeError("telegram down")))

    for _ in range(4):
        await worker.process_pending()
        assert (await job(pg_factory, order_id)).processed_at is None
        await make_due(pg_factory, order_id)
    await worker.process_pending()

    assert (await job(pg_factory, order_id)).processed_at is not None


async def test_ticket_issued_message_escapes_event_title_for_html(pg_factory):
    order_id, event_id = await paid_order(pg_factory)
    async with pg_factory() as session, session.begin():
        await session.execute(
            update(Event).where(Event.id == event_id).values(title="Кино <ночью> & вино")
        )
    sender = Sender()

    await TicketIssuedOutboxWorker(pg_factory, sender).process_pending()

    _, message = sender.calls[0]
    assert "Кино &lt;ночью&gt; &amp; вино" in message.text
