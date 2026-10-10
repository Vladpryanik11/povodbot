import { ChevronRight, Ticket as TicketIcon } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import type { Ticket } from '../api/types';
import { formatDateTime, ticketsLabel } from '../lib/format';
import { STATUS_LABEL, useTickets } from '../tickets/useTickets';
import { EmptyState } from '../ui/EmptyState';
import { ErrorState } from '../ui/ErrorState';
import { ICON_STROKE } from '../ui/icons';
import { Poster } from '../ui/Poster';
import { Skeleton } from '../ui/Skeleton';
import styles from './Tickets.module.css';

interface Group {
  eventId: string;
  tickets: Ticket[];
}

function groupByEvent(tickets: Ticket[]): Group[] {
  const groups = new Map<string, Ticket[]>();
  for (const ticket of tickets) groups.set(ticket.eventId, [...(groups.get(ticket.eventId) ?? []), ticket]);
  return [...groups.entries()].map(([eventId, list]) => ({
    eventId,
    tickets: list.sort((a, b) => a.position - b.position),
  }));
}

export function Tickets() {
  const navigate = useNavigate();
  const { tickets, fromCache, isPending, isError, refetch } = useTickets();

  if (isError) {
    return (
      <ErrorState
        title="Нет связи"
        text="Проверьте интернет. Оплаченные билеты никуда не денутся."
        actionLabel="Повторить"
        onAction={refetch}
      />
    );
  }
  if (isPending && !tickets) {
    return (
      <div className={styles.page}>
        <Skeleton height={96} />
        <Skeleton height={96} />
      </div>
    );
  }
  if (!tickets || tickets.length === 0) {
    return (
      <EmptyState
        icon={TicketIcon}
        title="Билетов пока нет"
        text="Выберите вечер в афише — билеты появятся здесь."
        action={{ label: 'Открыть афишу', onClick: () => navigate('/') }}
      />
    );
  }

  const now = Date.now();
  const upcoming = groupByEvent(tickets.filter((t) => Date.parse(t.startsAt) > now));
  const past = tickets.filter((t) => Date.parse(t.startsAt) <= now);

  return (
    <main className={styles.page}>
      <h1 className={`t-h1 ${styles.title}`}>Билеты</h1>
      {fromCache ? <p className={styles.cached}>Билет сохранён на телефоне</p> : null}
      {upcoming.length ? (
        <section className={styles.section} aria-labelledby="upcoming">
          <h2 id="upcoming" className={`t-h3 ${styles.sectionTitle}`}>
            Ближайшие
          </h2>
          {upcoming.map((group) => (
            <EventGroup key={group.eventId} group={group} />
          ))}
        </section>
      ) : null}
      {past.length ? (
        <details className={styles.past}>
          <summary className={styles.pastSummary}>Прошедшие · {past.length}</summary>
          <ul className={styles.pastList}>
            {past.map((ticket) => (
              <li key={ticket.id} className={styles.pastRow}>
                <span>
                  <span className={styles.rowTitle}>{ticket.eventTitle}</span>
                  <span className={styles.rowMeta}>{formatDateTime(ticket.startsAt, ticket.timezone)}</span>
                </span>
                <span className={styles.muted}>{STATUS_LABEL[ticket.status]}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </main>
  );
}

function EventGroup({ group }: { group: Group }) {
  const first = group.tickets[0];
  const valid = group.tickets.filter((t) => t.status === 'valid');
  const target = valid[0] ?? first;
  return (
    <Link to={`/tickets/${target.id}`} className={`${styles.card} ${valid.length ? '' : styles.inactive}`}>
      <Poster poster={first.poster} title={first.eventTitle} ratio="3:1" icon="film" className={styles.strip} />
      <span className={styles.cardBody}>
        <span>
          <span className={styles.rowTitle}>{first.eventTitle}</span>
          <span className={styles.rowMeta}>{formatDateTime(first.startsAt, first.timezone)}</span>
          {valid.length ? (
            <span className={styles.count}>{ticketsLabel(valid.length)}</span>
          ) : (
            <span className={styles.muted}>{STATUS_LABEL[first.status]}</span>
          )}
        </span>
        <ChevronRight size={20} strokeWidth={ICON_STROKE} aria-hidden="true" />
      </span>
    </Link>
  );
}
