import { useQuery } from '@tanstack/react-query';
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

/** Tickets from the server, falling back to the copy on the phone when offline. */
export function useTickets() {
  const api = useApi();
  const query = useQuery({
    queryKey: ['tickets'],
    queryFn: async () => {
      const tickets = await api.tickets();
      ticketCache.save(tickets);
      return tickets;
    },
  });
  const cached: Ticket[] = query.isError ? ticketCache.load() : [];
  const tickets = query.data ?? (cached.length ? cached : undefined);
  return {
    tickets,
    fromCache: !query.data && cached.length > 0,
    isPending: query.isPending,
    isError: query.isError && cached.length === 0,
    refetch: () => void query.refetch(),
  };
}
