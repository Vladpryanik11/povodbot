import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { useApi } from '../api/ApiProvider';
import { useDirections } from '../api/useDirections';
import { dayKey } from '../lib/format';
import { Billboard } from '../ui/Billboard';
import { DateStrip } from '../ui/DateStrip';
import { EmptyState } from '../ui/EmptyState';
import { ErrorState } from '../ui/ErrorState';
import { FilterChips } from '../ui/FilterChips';
import { useGlow } from '../ui/Glow';
import { PosterRow } from '../ui/PosterRow';
import { ReservationPlaque } from '../ui/ReservationPlaque';
import { Skeleton } from '../ui/Skeleton';
import styles from './Home.module.css';

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;
const MOSCOW = 'Europe/Moscow';

/** Showcase: filters, date strip, billboard, «На этой неделе» 16:9, «Скоро» 4:5 (spec v2 §5). */
export function Home() {
  const api = useApi();
  const directions = useDirections();
  const events = useQuery({ queryKey: ['events', 'all'], queryFn: () => api.events() });
  const me = useQuery({ queryKey: ['me'], queryFn: () => api.me() });
  const [directionId, setDirectionId] = useState<string | null>(null);
  const [day, setDay] = useState<string | null>(null);
  const [color, setColor] = useState<string | null>(null);

  const now = Date.now();
  const all = events.data ?? [];
  const ofDirection = useMemo(() => all.filter((e) => !directionId || e.directionId === directionId), [all, directionId]);
  const marked = useMemo(() => new Set(ofDirection.map((e) => dayKey(e.startsAt, e.timezone))), [ofDirection]);
  const shown = day ? ofDirection.filter((e) => dayKey(e.startsAt, e.timezone) === day) : ofDirection;
  const thisWeek = shown.filter((e) => Date.parse(e.startsAt) - now <= WEEK_MS);
  const later = shown.filter((e) => Date.parse(e.startsAt) - now > WEEK_MS);
  // The glow follows the billboard slide; no billboard, no glow.
  useGlow(shown.length > 0 ? color : null);

  const plaque = me.data?.activeOrder ? <ReservationPlaque order={me.data.activeOrder} /> : null;

  if (events.isError) {
    return (
      <main className={styles.page}>
        <ErrorState
          title="Нет связи"
          text="Проверь интернет. Купленные билеты никуда не денутся."
          actionLabel="Повторить"
          onAction={() => void events.refetch()}
        />
      </main>
    );
  }

  if (events.isPending) {
    return (
      <main className={styles.page}>
        <div className={styles.loading}>
          <Skeleton height={44} />
          <Skeleton height={320} />
        </div>
      </main>
    );
  }

  if (all.length === 0) {
    return (
      <main className={styles.page}>
        <EmptyState title="Пока тихо" text="Новых вечеров нет. Как появятся — маякнём в боте." />
        {plaque}
      </main>
    );
  }

  return (
    <main className={styles.page}>
      <div className={styles.filters}>
        <FilterChips items={directions} value={directionId} onChange={setDirectionId} />
        <DateStrip from={now} days={14} marked={marked} value={day} onChange={setDay} timeZone={MOSCOW} />
      </div>
      {shown.length === 0 ? (
        <EmptyState
          title="Пока тихо"
          text="Новых вечеров нет. Как появятся — маякнём в боте."
          action={{
            label: 'Показать все',
            onClick: () => {
              setDirectionId(null);
              setDay(null);
            },
          }}
        />
      ) : (
        <>
          <Billboard events={shown} now={now} onColor={setColor} />
          <PosterRow title="На этой неделе" variant="wide" events={thisWeek} now={now} />
          <PosterRow title="Скоро" variant="tall" events={later} now={now} />
        </>
      )}
      {plaque}
    </main>
  );
}
