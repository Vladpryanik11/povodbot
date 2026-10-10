import { describe, expect, it } from 'vitest';
import type { Me, Order } from './api/types';
import { normalizeLaunchHash, resolveStart } from './start';

const me = (activeOrder: Partial<Order> | null = null): Me => ({
  welcomeAccepted: true,
  activeOrder: activeOrder as Order | null,
  showInAttendees: false,
});

describe('resolveStart', () => {
  it('maps every deep link kind to its screen', () => {
    expect(resolveStart('event_e2', me())).toBe('/events/e2');
    expect(resolveStart('order_o9', me())).toBe('/order/o9');
    expect(resolveStart('ticket_tk-1', me())).toBe('/tickets/tk-1');
    expect(resolveStart('claim_s1tk1', me())).toBe('/claim/s1tk1');
    expect(resolveStart('vote_p-film', me())).toBe('/polls');
  });

  it('sends a guest with a live reservation to it, whatever the link says', () => {
    expect(resolveStart('event_e2', me({ id: 'o1', status: 'pending' }))).toBe('/order/o1');
    expect(resolveStart(null, me({ id: 'o1', status: 'failed' }))).toBe('/order/o1');
  });

  it('falls back to the afisha for missing or unknown parameters', () => {
    expect(resolveStart(null, me())).toBe('/');
    expect(resolveStart('garbage', me())).toBe('/');
    expect(resolveStart('event_', me())).toBe('/');
  });
});

describe('normalizeLaunchHash', () => {
  it('replaces the launch parameters Telegram puts after # with the afisha route', () => {
    expect(normalizeLaunchHash('#tgWebAppData=query_id%3D1&tgWebAppVersion=7.10&tgWebAppPlatform=ios')).toBe('#/');
    expect(normalizeLaunchHash('')).toBe('#/');
    expect(normalizeLaunchHash('#')).toBe('#/');
  });

  it('leaves real app routes alone', () => {
    expect(normalizeLaunchHash('#/events/e-film')).toBeNull();
    expect(normalizeLaunchHash('#/')).toBeNull();
  });
});
