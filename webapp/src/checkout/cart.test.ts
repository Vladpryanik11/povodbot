import { describe, expect, it } from 'vitest';
import { cartReducer, cartTotal, fitCart } from './cart';

const offers = [
  { id: 'a', name: 'Входной', priceKopecks: 155000, seatsLeft: 3 },
  { id: 'b', name: 'С другом', priceKopecks: 160000, seatsLeft: 1 },
];

describe('cartReducer', () => {
  it('never goes below zero or above the seats of the type', () => {
    let cart = cartReducer({}, { type: 'dec', ticketTypeId: 'a', max: 3 });
    expect(cart.a ?? 0).toBe(0);
    for (let i = 0; i < 5; i++) cart = cartReducer(cart, { type: 'inc', ticketTypeId: 'a', max: 3 });
    expect(cart.a).toBe(3);
  });

  it('sets a quantity directly', () => {
    expect(cartReducer({ a: 3 }, { type: 'set', ticketTypeId: 'a', qty: 2 })).toEqual({ a: 2 });
  });
});

describe('cartTotal', () => {
  it('counts tickets and sums kopecks across types', () => {
    expect(cartTotal({ a: 2, b: 1 }, offers)).toEqual({ count: 3, kopecks: 470000 });
    expect(cartTotal({ a: 3 }, offers)).toEqual({ count: 3, kopecks: 465000 });
    expect(cartTotal({}, offers)).toEqual({ count: 0, kopecks: 0 });
  });
});

describe('fitCart', () => {
  it('trims the cart to the seats left, taking from the last types first', () => {
    expect(fitCart({ a: 3 }, offers, 2)).toEqual({ a: 2 });
    expect(fitCart({ a: 2, b: 1 }, offers, 2)).toEqual({ a: 2, b: 0 });
    expect(fitCart({ a: 1 }, offers, 5)).toEqual({ a: 1 });
  });
});
