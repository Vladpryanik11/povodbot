import { describe, expect, it } from 'vitest';
import { ApiError } from '../AppApi';
import { MockApi, type Scenario } from './MockApi';

const T0 = Date.parse('2026-10-10T09:00:00Z');

function api(scenario: Scenario = 'happy', clock = { t: T0 }) {
  return new MockApi({ scenario, latencyMs: 0, now: () => clock.t });
}

async function rejection(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError);
    return error as ApiError;
  }
  throw new Error('expected a rejection');
}

describe('MockApi fixtures', () => {
  it('lists future events by date with the film night first on Friday 16 Oct at 20:00 MSK', async () => {
    const events = await api().events();
    expect(events[0].title).toBe('Повод для киновечера');
    expect(events[0].startsAt).toBe('2026-10-16T17:00:00.000Z');
    expect(events[0].seatsLeft).toBe(5);
    expect(events.some((e) => e.address === null)).toBe(true);
    expect(events.some((e) => e.soldOut)).toBe(true);
    expect(events.some((e) => e.poster === null)).toBe(true);
  });

  it('filters by direction', async () => {
    const mock = api();
    const [, games] = await mock.directions();
    const events = await mock.events(games.id);
    expect(events.length).toBeGreaterThan(0);
    expect(events.every((e) => e.directionId === games.id)).toBe(true);
  });
});

describe('orders', () => {
  it('refuses a second active reservation and names the first', async () => {
    const mock = api();
    const [film] = await mock.events();
    const detail = await mock.event(film.id);
    const first = await mock.createOrder(film.id, [{ ticketTypeId: detail.ticketTypes[0].id, qty: 1 }]);
    const error = await rejection(
      mock.createOrder(film.id, [{ ticketTypeId: detail.ticketTypes[0].id, qty: 1 }]),
    );
    expect(error.code).toBe('active_order_exists');
    expect(error.data.orderId).toBe(first.id);
    expect((await mock.me()).activeOrder?.id).toBe(first.id);
  });

  it('reports how many seats are left when the cart asks for more', async () => {
    const mock = api('sold_out');
    const [film] = await mock.events();
    const detail = await mock.event(film.id);
    const error = await rejection(
      mock.createOrder(film.id, [{ ticketTypeId: detail.ticketTypes[0].id, qty: 3 }]),
    );
    expect(error.code).toBe('not_enough_seats');
    expect(error.data.seatsLeft).toBe(2);
  });

  it('expires a pending order after ten minutes', async () => {
    const clock = { t: T0 };
    const mock = api('happy', clock);
    const [film] = await mock.events();
    const detail = await mock.event(film.id);
    const order = await mock.createOrder(film.id, [{ ticketTypeId: detail.ticketTypes[0].id, qty: 2 }]);
    expect(order.totalKopecks).toBe(310000);
    expect(Date.parse(order.expiresAt) - T0).toBe(10 * 60 * 1000);
    clock.t = T0 + 10 * 60 * 1000 + 1;
    expect((await mock.order(order.id)).status).toBe('expired');
    expect((await mock.me()).activeOrder).toBeNull();
  });

  it('issues tickets when the mock payment succeeds', async () => {
    const mock = api();
    const [film] = await mock.events();
    const detail = await mock.event(film.id);
    const order = await mock.createOrder(film.id, [{ ticketTypeId: detail.ticketTypes[0].id, qty: 2 }]);
    await mock.completePayment(order.id, 'paid');
    expect((await mock.order(order.id)).status).toBe('paid');
    const fresh = (await mock.tickets()).filter((t) => t.eventId === film.id && t.status === 'valid');
    expect(fresh.length).toBeGreaterThanOrEqual(2);
  });

  it('keeps the bank answer uncertain in pay_pending and refuses to cancel', async () => {
    const mock = api('pay_pending');
    const [film] = await mock.events();
    const detail = await mock.event(film.id);
    const order = await mock.createOrder(film.id, [{ ticketTypeId: detail.ticketTypes[0].id, qty: 1 }]);
    await mock.completePayment(order.id, 'paid');
    const after = await mock.order(order.id);
    expect(after.status).toBe('pending');
    expect(after.paymentUncertain).toBe(true);
    expect((await rejection(mock.cancelOrder(order.id))).code).toBe('payment_uncertain');
  });

  it('turns any payment into a failure in pay_fail and into manual reconciliation in late', async () => {
    for (const [scenario, status] of [
      ['pay_fail', 'failed'],
      ['late', 'reconciliation'],
    ] as const) {
      const mock = api(scenario);
      const [film] = await mock.events();
      const detail = await mock.event(film.id);
      const order = await mock.createOrder(film.id, [{ ticketTypeId: detail.ticketTypes[0].id, qty: 1 }]);
      await mock.completePayment(order.id, 'paid');
      expect((await mock.order(order.id)).status).toBe(status);
    }
  });
});

describe('polls', () => {
  it('hides percentages until the vote, then lets the user change it without double counting', async () => {
    const mock = api();
    const [poll] = (await mock.polls()).filter((p) => !p.closed);
    expect(poll.options.every((o) => o.percent === null)).toBe(true);
    const first = await mock.vote(poll.id, poll.options[0].id);
    expect(first.myOptionId).toBe(poll.options[0].id);
    expect(first.options.every((o) => o.percent !== null)).toBe(true);
    const second = await mock.vote(poll.id, poll.options[1].id);
    expect(second.myOptionId).toBe(poll.options[1].id);
    expect(second.votes).toBe(first.votes);
  });

  it('refuses votes after the closing time', async () => {
    const clock = { t: T0 };
    const mock = api('happy', clock);
    const [poll] = (await mock.polls()).filter((p) => !p.closed);
    clock.t = Date.parse(poll.closesAt) + 1;
    expect((await rejection(mock.vote(poll.id, poll.options[0].id))).code).toBe('poll_closed');
  });
});

describe('ticket sharing', () => {
  it('lets a friend claim once and hides the QR from the buyer', async () => {
    const mock = api();
    const valid = (await mock.tickets()).find((t) => t.status === 'valid')!;
    const { shareUrl } = await mock.shareTicket(valid.id);
    const token = new URL(shareUrl).searchParams.get('startapp')!.replace('claim_', '');
    const claimed = await mock.claimTicket(token);
    expect(claimed.status).toBe('valid');
    expect(claimed.qrToken).not.toBeNull();
    const original = (await mock.tickets()).find((t) => t.id === valid.id)!;
    expect(original.status).toBe('transferred');
    expect(original.qrToken).toBeNull();
    expect((await rejection(mock.claimTicket(token))).code).toBe('already_claimed');
  });
});

describe('scenarios', () => {
  it('empty has no events, tickets or polls', async () => {
    const mock = api('empty');
    expect(await mock.events()).toEqual([]);
    expect(await mock.tickets()).toEqual([]);
    expect(await mock.polls()).toEqual([]);
  });

  it('offline rejects every call with a network error', async () => {
    const mock = api('offline');
    expect((await rejection(mock.events())).code).toBe('network');
    expect((await rejection(mock.me())).code).toBe('network');
  });
});
