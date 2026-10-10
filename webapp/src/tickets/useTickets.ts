import { useQuery } from '@tanstack/react-query';
import type { AppApi } from '../api/AppApi';
import { useApi } from '../api/ApiProvider';
import type { Ticket, TicketStatus } from '../api/types';
import { ticketCache } from '../lib/ticketCache';

export const STATUS_LABEL: Record<TicketStatus, string> = {
  valid: 'Действителен',
  used: 'Использован',
  returned: 'Возвращён',
  transferred: 'Передан',
  event_cancelled: 'Вечер отменён',
};

/** The tickets query; also used to prefetch right after a payment so the QR is on the phone. */
export function ticketsQuery(api: AppApi) {
  return {
    queryKey: ['tickets'],
    queryFn: async () => {
      const tickets = await api.tickets();
      ticketCache.save(tickets);
      return tickets;
    },
  };
}

/** Tickets from the server; the copy on the phone shows at once and stays when offline. */
export function useTickets() {
  const api = useApi();
  const query = useQuery({
    ...ticketsQuery(api),
    placeholderData: () => {
      const saved = ticketCache.load();
      return saved.length ? saved : undefined;
    },
  });
  const cached: Ticket[] = query.isError ? ticketCache.load() : [];
  const tickets = query.data ?? (cached.length ? cached : undefined);
  return {
    tickets,
    fromCache: query.isPlaceholderData || (!query.data && cached.length > 0),
    isPending: query.isPending,
    isError: query.isError && cached.length === 0,
    refetch: () => void query.refetch(),
  };
}
