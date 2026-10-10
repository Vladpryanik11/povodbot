import { useQuery } from '@tanstack/react-query';
import { QrCode } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { useApi } from '../api/ApiProvider';
import type { Ticket } from '../api/types';
import { dayKey, formatTime } from '../lib/format';
import { posterColor } from '../lib/posterColor';
import { useTickets } from '../tickets/useTickets';
import { ICON_STROKE } from './icons';
import { TAB_PATHS } from './TabBar';
import styles from './TodayPill.module.css';

/** Doors are long closed six hours after the start; the pill would only get in the way. */
const STALE_MS = 6 * 60 * 60 * 1000;

/** The first valid ticket for an evening today that has not been over for long. */
export function pickTodayTicket(tickets: Ticket[], now: number): Ticket | null {
  const nowIso = new Date(now).toISOString();
  return (
    tickets.find(
      (t) =>
        t.status === 'valid' &&
        dayKey(t.startsAt, t.timezone) === dayKey(nowIso, t.timezone) &&
        Date.parse(t.startsAt) + STALE_MS > now,
    ) ?? null
  );
}

/** Glass pill above the tab bar on the day of an evening; tap opens the ticket's QR (spec v2 §4). */
export function TodayPill() {
  const api = useApi();
  const { pathname } = useLocation();
  const { tickets } = useTickets();
  const me = useQuery({ queryKey: ['me'], queryFn: () => api.me() });

  if (!TAB_PATHS.has(pathname)) return null;
  // On Home a live reservation's plaque takes this place (spec v2 §5, item 6).
  if (pathname === '/' && me.data?.activeOrder) return null;
  const ticket = pickTodayTicket(tickets ?? [], Date.now());
  if (!ticket) return null;

  const time = formatTime(ticket.startsAt, ticket.timezone);
  return (
    <Link to={`/tickets/${ticket.id}`} className={`glass ${styles.pill}`} aria-label={`Сегодня · ${time} · ${ticket.eventTitle}. Билет`}>
      {ticket.poster ? (
        <img className={styles.thumb} src={ticket.poster.url} alt="" aria-hidden="true" />
      ) : (
        <span className={styles.thumb} style={{ backgroundColor: posterColor(ticket.eventTitle) }} aria-hidden="true" />
      )}
      <span className={styles.when}>Сегодня · {time}</span>
      <span className={styles.title}>{ticket.eventTitle}</span>
      <QrCode size={20} strokeWidth={ICON_STROKE} aria-hidden="true" />
    </Link>
  );
}
