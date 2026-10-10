import { ApiError, type AppApi } from '../AppApi';
import type { Direction, EventCard, EventDetail, Me, Order, OrderItem, Poll, Ticket } from '../types';
import { buildFixtures, MOSCOW, type Fixtures, type MockEvent, type MockPoll } from './fixtures';

export type Scenario = 'happy' | 'pay_fail' | 'pay_pending' | 'late' | 'sold_out' | 'empty' | 'offline';

export const SCENARIOS: Scenario[] = ['happy', 'pay_fail', 'pay_pending', 'late', 'sold_out', 'empty', 'offline'];

export function scenarioFromUrl(search: string = typeof window === 'undefined' ? '' : window.location.search): Scenario {
  const value = new URLSearchParams(search).get('scenario');
  return SCENARIOS.includes(value as Scenario) ? (value as Scenario) : 'happy';
}

export const SHARE_BASE_URL = 'https://t.me/povod_club_bot/app';
const RESERVATION_MS = 10 * 60 * 1000;
const WELCOME_KEY = 'povod.mock.welcome';

interface MockApiOptions {
  scenario?: Scenario;
  now?: () => number;
  latencyMs?: number;
  fixtures?: Fixtures;
}

type MockOrder = Order & { reserved: { ticketTypeId: string; qty: number }[] };

export class MockApi implements AppApi {
  readonly scenario: Scenario;
  private readonly now: () => number;
  private readonly latencyMs: number;
  private readonly data: Fixtures;
  private readonly orders = new Map<string, MockOrder>();
  private readonly shares = new Map<string, { ticketId: string; claimed: boolean }>();
  private seq = 0;

  constructor(options: MockApiOptions = {}) {
    this.scenario = options.scenario ?? 'happy';
    this.now = options.now ?? Date.now;
    this.latencyMs = options.latencyMs ?? 300;
    this.data = options.fixtures ?? buildFixtures(this.now());
    if (this.scenario === 'sold_out') {
      const first = this.data.events[0];
      if (first) first.serverSeatsLeft = Math.min(2, first.seatsLeft);
    }
  }

  // ---- AppApi -------------------------------------------------------------

  me(): Promise<Me> {
    return this.call(() => ({
      welcomeAccepted: readWelcome(),
      activeOrder: this.activeOrder(),
    }));
  }

  acceptWelcome(): Promise<void> {
    return this.call(() => {
      writeWelcome();
    });
  }

  directions(): Promise<Direction[]> {
    return this.call(() => this.data.directions.map((d) => ({ ...d })));
  }

  events(directionId?: string): Promise<EventCard[]> {
    return this.call(() =>
      this.visibleEvents()
        .filter((e) => !directionId || e.directionId === directionId)
        .map((e) => toCard(e)),
    );
  }

  event(id: string): Promise<EventDetail> {
    return this.call(() => {
      const event = this.findEvent(id);
      const poll = this.data.polls.find((p) => p.eventId === id);
      return {
        ...toCard(event),
        description: event.description,
        mapUrl: event.mapUrl,
        ticketTypes: event.ticketTypes.map((t) => ({ ...t })),
        poll: poll ? this.pollView(poll) : null,
      };
    });
  }

  createOrder(eventId: string, items: OrderItem[]): Promise<Order> {
    return this.call(() => {
      const active = this.activeOrder();
      if (active) throw new ApiError('active_order_exists', { orderId: active.id, eventTitle: active.eventTitle });
      const event = this.findEvent(eventId);
      const wanted = items.filter((i) => i.qty > 0);
      const count = wanted.reduce((sum, i) => sum + i.qty, 0);
      const available = event.serverSeatsLeft ?? event.seatsLeft;
      if (count === 0 || count > available) throw new ApiError('not_enough_seats', { seatsLeft: available });
      let total = 0;
      for (const item of wanted) {
        const type = event.ticketTypes.find((t) => t.id === item.ticketTypeId);
        if (!type) throw new ApiError('not_found');
        if (item.qty > type.seatsLeft) throw new ApiError('not_enough_seats', { seatsLeft: type.seatsLeft });
        total += type.priceKopecks * item.qty;
      }
      this.hold(event, wanted, -1);
      const id = `o-${++this.seq}`;
      const order: MockOrder = {
        id,
        eventId: event.id,
        eventTitle: event.title,
        startsAt: event.startsAt,
        timezone: event.timezone,
        status: 'pending',
        expiresAt: new Date(this.now() + RESERVATION_MS).toISOString(),
        paymentUrl: `#/mock-pay/${id}`,
        items: wanted.map((i) => ({ ...i })),
        totalKopecks: total,
        paymentUncertain: false,
        reserved: wanted.map((i) => ({ ...i })),
      };
      this.orders.set(id, order);
      return publicOrder(order);
    });
  }

  order(id: string): Promise<Order> {
    return this.call(() => publicOrder(this.refreshed(this.findOrder(id))));
  }

  cancelOrder(id: string): Promise<void> {
    return this.call(() => {
      const order = this.refreshed(this.findOrder(id));
      if (order.paymentUncertain) throw new ApiError('payment_uncertain');
      if (order.status === 'pending' || order.status === 'failed') {
        order.status = 'cancelled';
        this.release(order);
      }
    });
  }

  tickets(): Promise<Ticket[]> {
    return this.call(() => {
      if (this.scenario === 'empty') return [];
      return [...this.data.tickets].sort((a, b) => a.startsAt.localeCompare(b.startsAt)).map((t) => ({ ...t }));
    });
  }

  shareTicket(id: string): Promise<{ shareUrl: string }> {
    return this.call(() => {
      const ticket = this.findTicket(id);
      if (ticket.status !== 'valid') throw new ApiError('not_found');
      const token = `s${++this.seq}${id.replace(/[^a-z0-9]/gi, '')}`;
      this.shares.set(token, { ticketId: id, claimed: false });
      return { shareUrl: `${SHARE_BASE_URL}?startapp=claim_${token}` };
    });
  }

  revokeShare(id: string): Promise<void> {
    return this.call(() => {
      for (const [token, share] of this.shares) {
        if (share.ticketId !== id) continue;
        if (share.claimed) throw new ApiError('already_claimed');
        this.shares.delete(token);
      }
    });
  }

  claimTicket(token: string): Promise<Ticket> {
    return this.call(() => {
      const share = this.shares.get(token);
      if (!share) throw new ApiError('not_found');
      if (share.claimed) throw new ApiError('already_claimed');
      share.claimed = true;
      const original = this.findTicket(share.ticketId);
      const claimed: Ticket = { ...original, id: `${original.id}-friend`, status: 'valid' };
      original.status = 'transferred';
      original.qrToken = null;
      return claimed;
    });
  }

  polls(): Promise<Poll[]> {
    return this.call(() => (this.scenario === 'empty' ? [] : this.data.polls.map((p) => this.pollView(p))));
  }

  vote(pollId: string, optionId: string): Promise<Poll> {
    return this.call(() => {
      const poll = this.data.polls.find((p) => p.id === pollId);
      if (!poll) throw new ApiError('not_found');
      if (poll.closed || this.now() > Date.parse(poll.closesAt)) throw new ApiError('poll_closed');
      const next = poll.options.find((o) => o.id === optionId);
      if (!next) throw new ApiError('not_found');
      const previous = poll.options.find((o) => o.id === poll.myOptionId);
      if (previous) previous.count -= 1;
      next.count += 1;
      poll.myOptionId = optionId;
      return this.pollView(poll);
    });
  }

  // ---- Mock-only controls -------------------------------------------------

  /** What the bank page decides; scenarios override the guest's choice. */
  completePayment(orderId: string, outcome: 'paid' | 'failed'): Promise<Order> {
    return this.call(() => {
      const order = this.refreshed(this.findOrder(orderId));
      if (order.status !== 'pending' && order.status !== 'failed') return publicOrder(order);
      const result =
        this.scenario === 'pay_fail'
          ? 'failed'
          : this.scenario === 'pay_pending'
            ? 'uncertain'
            : this.scenario === 'late' && outcome === 'paid'
              ? 'late'
              : outcome;
      if (result === 'uncertain') {
        order.status = 'pending';
        order.paymentUncertain = true;
      } else if (result === 'late') {
        order.status = 'reconciliation';
        this.release(order);
      } else if (result === 'failed') {
        order.status = 'failed';
      } else {
        order.status = 'paid';
        this.issueTickets(order);
      }
      return publicOrder(order);
    });
  }

  // ---- internals ----------------------------------------------------------

  private async call<T>(fn: () => T): Promise<T> {
    if (this.latencyMs > 0) await new Promise((resolve) => setTimeout(resolve, this.latencyMs));
    if (this.scenario === 'offline') throw new ApiError('network');
    return fn();
  }

  private visibleEvents(): MockEvent[] {
    if (this.scenario === 'empty') return [];
    return this.data.events
      .filter((e) => Date.parse(e.startsAt) > this.now())
      .sort((a, b) => a.startsAt.localeCompare(b.startsAt));
  }

  private findEvent(id: string): MockEvent {
    const event = this.visibleEvents().find((e) => e.id === id);
    if (!event) throw new ApiError('not_found');
    return event;
  }

  private findOrder(id: string): MockOrder {
    const order = this.orders.get(id);
    if (!order) throw new ApiError('not_found');
    return order;
  }

  private findTicket(id: string): Ticket {
    const ticket = this.data.tickets.find((t) => t.id === id);
    if (!ticket) throw new ApiError('not_found');
    return ticket;
  }

  private activeOrder(): Order | null {
    for (const order of this.orders.values()) {
      const fresh = this.refreshed(order);
      if (fresh.status === 'pending' || fresh.status === 'failed') return publicOrder(fresh);
    }
    return null;
  }

  private refreshed(order: MockOrder): MockOrder {
    const live = order.status === 'pending' || order.status === 'failed';
    if (live && !order.paymentUncertain && this.now() > Date.parse(order.expiresAt)) {
      order.status = 'expired';
      this.release(order);
    }
    return order;
  }

  private hold(event: MockEvent, items: OrderItem[], sign: 1 | -1): void {
    for (const item of items) {
      const type = event.ticketTypes.find((t) => t.id === item.ticketTypeId);
      if (type) type.seatsLeft += sign * item.qty;
      event.seatsLeft += sign * item.qty;
      if (event.serverSeatsLeft !== undefined) event.serverSeatsLeft += sign * item.qty;
    }
  }

  private release(order: MockOrder): void {
    const event = this.data.events.find((e) => e.id === order.eventId);
    if (event && order.reserved.length) this.hold(event, order.reserved, 1);
    order.reserved = [];
  }

  private issueTickets(order: MockOrder): void {
    const event = this.data.events.find((e) => e.id === order.eventId)!;
    const count = order.items.reduce((sum, i) => sum + i.qty, 0);
    let position = 0;
    for (const item of order.items) {
      const type = event.ticketTypes.find((t) => t.id === item.ticketTypeId)!;
      for (let i = 0; i < item.qty; i++) {
        position += 1;
        const id = `${order.id}-t${position}`;
        this.data.tickets.push({
          id,
          eventId: event.id,
          eventTitle: event.title,
          startsAt: event.startsAt,
          timezone: event.timezone,
          address: event.address,
          mapUrl: event.mapUrl,
          typeName: type.name,
          position,
          ofCount: count,
          shortCode: String(1000 + ((this.seq * 37 + position * 101) % 9000)),
          status: 'valid',
          qrToken: `pv1.${id}.${Math.random().toString(36).slice(2, 12)}`,
          poster: event.poster,
        });
      }
    }
    order.reserved = [];
  }

  private pollView(poll: MockPoll): Poll {
    const votes = poll.options.reduce((sum, o) => sum + o.count, 0);
    const reveal = poll.closed || poll.myOptionId !== null;
    return {
      id: poll.id,
      question: poll.question,
      closesAt: poll.closesAt,
      timezone: MOSCOW,
      closed: poll.closed || this.now() > Date.parse(poll.closesAt),
      myOptionId: poll.myOptionId,
      votes,
      options: poll.options.map((o) => ({
        id: o.id,
        title: o.title,
        percent: reveal ? (votes ? Math.round((o.count / votes) * 100) : 0) : null,
      })),
    };
  }
}

function toCard(event: MockEvent): EventCard {
  return {
    id: event.id,
    title: event.title,
    startsAt: event.startsAt,
    timezone: event.timezone,
    address: event.address,
    poster: event.poster,
    minPriceKopecks: Math.min(...event.ticketTypes.map((t) => t.priceKopecks)),
    seatsLeft: event.seatsLeft,
    soldOut: event.seatsLeft <= 0,
    directionId: event.directionId,
  };
}

function publicOrder(order: MockOrder): Order {
  const { reserved: _reserved, ...rest } = order;
  return { ...rest, items: rest.items.map((i) => ({ ...i })) };
}

function readWelcome(): boolean {
  try {
    return window.localStorage.getItem(WELCOME_KEY) === '1';
  } catch {
    return false;
  }
}

function writeWelcome(): void {
  try {
    window.localStorage.setItem(WELCOME_KEY, '1');
  } catch {
    // Private mode: the welcome shows again next time, which is harmless.
  }
}
