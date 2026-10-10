import type { Ticket } from '../api/types';

const KEY = 'povod.tickets';

/** Last known tickets, so the QR opens at the door without a connection. Only valid tickets keep a token. */
export const ticketCache = {
  save(tickets: Ticket[]): void {
    const safe = tickets.map((t) => (t.status === 'valid' ? t : { ...t, qrToken: null }));
    try {
      localStorage.setItem(KEY, JSON.stringify(safe));
    } catch {
      // Storage full or blocked: the online list still works.
    }
  },
  load(): Ticket[] {
    try {
      const raw = localStorage.getItem(KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw) as Ticket[];
      if (!Array.isArray(parsed)) return [];
      return parsed.map((t) => (t.status === 'valid' ? t : { ...t, qrToken: null }));
    } catch {
      return [];
    }
  },
};
