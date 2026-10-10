import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { useApi } from '../api/ApiProvider';
import { useFavorites } from '../lib/favorites';
import { EmptyState } from '../ui/EmptyState';
import { FavButton } from '../ui/FavButton';
import { Skeleton } from '../ui/Skeleton';
import styles from './Favorites.module.css';

/** Saved evenings, upcoming first; past ones at the end, desaturated (spec v2 §5). */
export function Favorites() {
  const api = useApi();
  const favorites = useFavorites();
  const events = useQuery({ queryKey: ['events', 'all'], queryFn: () => api.events() });

  if (!favorites.ready || events.isPending) {
    return (
      <main className={styles.page}>
        <Skeleton height={240} />
      </main>
    );
  }

  const now = Date.now();
  const saved = (events.data ?? [])
    .filter((e) => favorites.has(e.id))
    .map((e) => ({ event: e, past: Date.parse(e.startsAt) <= now }))
    .sort((a, b) => Number(a.past) - Number(b.past) || a.event.startsAt.localeCompare(b.event.startsAt));

  return (
    <main className={styles.page}>
      <h1 className={`${styles.title} t-h1`}>Избранное</h1>
      {saved.length === 0 ? (
        <EmptyState title="Тут будут сохранённые вечера" text="Жми сердечко на афише — соберём всё здесь." />
      ) : (
        <ul className={styles.grid}>
          {saved.map(({ event, past }) => (
            <li key={event.id} className={styles.cell} data-past={past || undefined}>
              <Link to={`/events/${event.id}`} className={styles.card}>
                <div className={styles.poster}>
                  {event.poster ? <img src={event.poster.url} alt="" aria-hidden="true" loading="lazy" /> : null}
                </div>
                <span className={`${styles.name} t-h3`}>{event.title}</span>
              </Link>
              <div className={styles.fav}>
                <FavButton eventId={event.id} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
