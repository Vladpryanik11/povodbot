import type { OrderItem, TicketTypeOffer } from '../api/types';

/** Quantity per ticket type id. */
export type CartState = Record<string, number>;

export type CartAction =
  | { type: 'inc' | 'dec'; ticketTypeId: string; max: number }
  | { type: 'set'; ticketTypeId: string; qty: number }
  | { type: 'replace'; cart: CartState };

export function cartReducer(state: CartState, action: CartAction): CartState {
  if (action.type === 'replace') return { ...action.cart };
  const current = state[action.ticketTypeId] ?? 0;
  const next =
    action.type === 'set'
      ? action.qty
      : Math.min(action.max, Math.max(0, current + (action.type === 'inc' ? 1 : -1)));
  return { ...state, [action.ticketTypeId]: Math.max(0, next) };
}

export function cartTotal(cart: CartState, offers: Pick<TicketTypeOffer, 'id' | 'priceKopecks'>[]) {
  let count = 0;
  let kopecks = 0;
  for (const offer of offers) {
    const qty = cart[offer.id] ?? 0;
    count += qty;
    kopecks += qty * offer.priceKopecks;
  }
  return { count, kopecks };
}

/** Reduces the cart to `seats` tickets, removing from the last ticket types first. */
export function fitCart(cart: CartState, offers: Pick<TicketTypeOffer, 'id'>[], seats: number): CartState {
  const next = { ...cart };
  let excess = cartTotal(next, offers.map((o) => ({ id: o.id, priceKopecks: 0 }))).count - seats;
  for (const offer of [...offers].reverse()) {
    if (excess <= 0) break;
    const qty = next[offer.id] ?? 0;
    const cut = Math.min(qty, excess);
    if (offer.id in next) next[offer.id] = qty - cut;
    excess -= cut;
  }
  return next;
}

export function cartItems(cart: CartState): OrderItem[] {
  return Object.entries(cart)
    .filter(([, qty]) => qty > 0)
    .map(([ticketTypeId, qty]) => ({ ticketTypeId, qty }));
}
