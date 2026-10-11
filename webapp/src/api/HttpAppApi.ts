import { ApiError, type AppApi } from './AppApi';
import type { Direction, EventCard, EventDetail, Me, Order, Poll, Ticket } from './types';

/**
 * Real /api/app, read-only slice: directions, the afisha and one evening come from the server.
 * Buying, tickets and polls are not served yet: the guest has no orders or tickets here and
 * `createOrder` rejects with `sales_closed`, which the evening screen turns into "buy in the bot".
 */
export class HttpAppApi implements AppApi {
  private showInAttendees = false;

  constructor(private readonly base = '/api/app') {}

  private async get<T>(path: string): Promise<T> {
    let res: Response;
    try {
      res = await fetch(`${this.base}${path}`);
    } catch {
      throw new ApiError('network');
    }
    if (res.status === 404) throw new ApiError('not_found');
    if (!res.ok) throw new ApiError('network');
    return (await res.json()) as T;
  }

  async me(): Promise<Me> {
    return { activeOrder: null, showInAttendees: this.showInAttendees };
  }

  async setShowInAttendees(value: boolean): Promise<Me> {
    this.showInAttendees = value;
    return this.me();
  }

  directions(): Promise<Direction[]> {
    return this.get('/directions');
  }

  events(directionId?: string): Promise<EventCard[]> {
    return this.get(directionId ? `/events?direction_id=${encodeURIComponent(directionId)}` : '/events');
  }

  event(id: string): Promise<EventDetail> {
    return this.get(`/events/${encodeURIComponent(id)}`);
  }

  async createOrder(): Promise<Order> {
    throw new ApiError('sales_closed');
  }

  async order(): Promise<Order> {
    throw new ApiError('not_found');
  }

  async cancelOrder(): Promise<void> {}

  async tickets(): Promise<Ticket[]> {
    return [];
  }

  async shareTicket(): Promise<{ shareUrl: string }> {
    throw new ApiError('not_found');
  }

  async revokeShare(): Promise<void> {}

  async claimTicket(): Promise<Ticket> {
    throw new ApiError('not_found');
  }

  async polls(): Promise<Poll[]> {
    return [];
  }

  async vote(): Promise<Poll> {
    throw new ApiError('poll_closed');
  }
}
