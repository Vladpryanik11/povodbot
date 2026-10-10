import type { EventCard } from '../api/types';
import { dayKey } from '../lib/format';
import styles from './StatusPill.module.css';

type Props = { kind: 'today' | 'left' | 'soldout'; count?: number };

/** Dark pill on a poster; the dot carries the poster colour, the words stay white (spec v2 §5). */
export function StatusPill({ kind, count }: Props) {
  const text = kind === 'today' ? 'Сегодня' : kind === 'left' ? `Осталось ${count ?? 0}` : 'Мест нет';
  return (
    <span className={styles.pill}>
      {kind === 'soldout' ? null : <span className={styles.dot} data-dot="" aria-hidden="true" />}
      {text}
    </span>
  );
}

const LOW_SEATS = 15;

/** The pill a poster gets: sold out, tonight, or few seats left — otherwise none. */
export function PosterStatus({ event, now }: { event: EventCard; now: number }) {
  if (event.soldOut) return <StatusPill kind="soldout" />;
  if (dayKey(event.startsAt, event.timezone) === dayKey(new Date(now).toISOString(), event.timezone)) {
    return <StatusPill kind="today" />;
  }
  if (event.seatsLeft <= LOW_SEATS) return <StatusPill kind="left" count={event.seatsLeft} />;
  return null;
}
