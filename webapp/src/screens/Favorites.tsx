import { useQuery } from '@tanstack/react-query';
import { useApi } from '../api/ApiProvider';
import { useFavorites } from '../lib/favorites';
import { EmptyState } from '../ui/EmptyState';
import { PosterCard } from '../ui/PosterRow';
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
              <PosterCard event={event} variant="tall" now={now} />
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
