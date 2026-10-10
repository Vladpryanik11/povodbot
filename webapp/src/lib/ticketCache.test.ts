import { describe, expect, it } from 'vitest';
import { buildFixtures } from '../api/mock/fixtures';
import type { Ticket, TicketStatus } from '../api/types';
import { ticketCache } from './ticketCache';

const base = buildFixtures(Date.parse('2026-10-10T09:00:00Z')).tickets[0];
const make = (id: string, status: TicketStatus): Ticket => ({ ...base, id, status, qrToken: `pv1.${id}.secret` });

describe('ticketCache', () => {
  it('keeps QR tokens only for valid tickets', () => {
    ticketCache.save([
      make('a', 'valid'),
      make('b', 'returned'),
      make('c', 'transferred'),
      make('d', 'event_cancelled'),
      make('e', 'used'),
    ]);
    const loaded = ticketCache.load();
    expect(loaded.map((t) => [t.id, t.qrToken])).toEqual([
      ['a', 'pv1.a.secret'],
      ['b', null],
      ['c', null],
      ['d', null],
      ['e', null],
    ]);
  });

  it('returns an empty list when nothing was saved or the data is broken', () => {
    expect(ticketCache.load()).toEqual([]);
    localStorage.setItem('povod.tickets', '{not json');
    expect(ticketCache.load()).toEqual([]);
  });
});
