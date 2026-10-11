import type { Direction, EventCard, EventDetail, Me, Order, OrderItem, Poll, Ticket } from './types';

export type ApiErrorCode =
  | 'active_order_exists'
  | 'not_enough_seats'
  | 'poll_closed'
  | 'payment_uncertain'
  | 'already_claimed'
  | 'not_found'
  | 'network';

export class ApiError extends Error {
  constructor(
    public readonly code: ApiErrorCode,
    public readonly data: { orderId?: string; seatsLeft?: number; eventTitle?: string } = {},
  ) {
    super(code);
    this.name = 'ApiError';
  }
}

/** Contract of /api/app (spec section 5). Stage A implements it with MockApi. */
export interface AppApi {
  me(): Promise<Me>;
  setShowInAttendees(value: boolean): Promise<Me>;
  directions(): Promise<Direction[]>;
  events(directionId?: string): Promise<EventCard[]>;
  event(id: string): Promise<EventDetail>;
  createOrder(eventId: string, items: OrderItem[]): Promise<Order>;
  order(id: string): Promise<Order>;
  cancelOrder(id: string): Promise<void>;
  tickets(): Promise<Ticket[]>;
  shareTicket(id: string): Promise<{ shareUrl: string }>;
  revokeShare(id: string): Promise<void>;
  claimTicket(token: string): Promise<Ticket>;
  polls(): Promise<Poll[]>;
  vote(pollId: string, optionId: string): Promise<Poll>;
}
