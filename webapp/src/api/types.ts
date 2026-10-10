export type DirectionIcon = 'film' | 'dice' | 'talk' | 'party';

export interface Direction {
  id: string;
  title: string;
  icon: DirectionIcon;
}

export interface Poster {
  url: string;
  /** 0–1 focus point the owner tapped; becomes object-position. */
  focusX: number;
  focusY: number;
  width: number;
  height: number;
}

export interface EventCard {
  id: string;
  title: string;
  startsAt: string;
  timezone: string;
  /** null while the venue is still being decided. */
  address: string | null;
  poster: Poster | null;
  minPriceKopecks: number;
  seatsLeft: number;
  soldOut: boolean;
  directionId: string;
}

export interface TicketTypeOffer {
  id: string;
  name: string;
  priceKopecks: number;
  seatsLeft: number;
}

export interface PollOption {
  id: string;
  title: string;
  /** Hidden (null) until the current user has voted or the poll is closed. */
  percent: number | null;
}

export interface Poll {
  id: string;
  question: string;
  closesAt: string;
  timezone: string;
  closed: boolean;
  options: PollOption[];
  myOptionId: string | null;
  votes: number;
}

export interface EventDetail extends EventCard {
  description: string;
  mapUrl: string | null;
  ticketTypes: TicketTypeOffer[];
  poll: Poll | null;
}

export type OrderStatus = 'pending' | 'paid' | 'failed' | 'expired' | 'cancelled' | 'reconciliation';

export interface OrderItem {
  ticketTypeId: string;
  qty: number;
}

export interface Order {
  id: string;
  eventId: string;
  eventTitle: string;
  startsAt: string;
  timezone: string;
  status: OrderStatus;
  expiresAt: string;
  paymentUrl: string;
  items: OrderItem[];
  totalKopecks: number;
  /** The bank has not given a definite answer yet; the reservation must not be cancelled. */
  paymentUncertain: boolean;
}

export type TicketStatus = 'valid' | 'used' | 'returned' | 'transferred' | 'event_cancelled';

export interface Ticket {
  id: string;
  eventId: string;
  eventTitle: string;
  startsAt: string;
  timezone: string;
  address: string | null;
  mapUrl: string | null;
  typeName: string;
  position: number;
  ofCount: number;
  shortCode: string;
  status: TicketStatus;
  /** Only valid tickets carry a token. */
  qrToken: string | null;
  poster: Poster | null;
}

export interface Me {
  welcomeAccepted: boolean;
  activeOrder: Order | null;
}
