import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { OwnerApiError } from '../../api/owner/OwnerApi';
import { useOwnerApi } from '../../api/owner/OwnerApiProvider';
import type { OwnerEventListItem, OwnerFilter } from '../../api/owner/types';
import { formatDateTime } from '../../lib/format';
import { CLUB_TIMEZONE } from '../../owner/form';
import { ownerStatus } from '../../owner/status';
import { useBackButton, useMainButton } from '../../telegram/hooks';
import { EmptyState } from '../../ui/EmptyState';
import { FilterChips } from '../../ui/FilterChips';
import { Pill } from '../../ui/Pill';
import { Skeleton } from '../../ui/Skeleton';
import { OwnerLoadError } from './OwnerLoadError';
import styles from './OwnerEvents.module.css';

const FILTERS = [
  { id: 'draft', title: 'Черновики' },
  { id: 'past', title: 'Прошли' },
];

const EMPTY: Record<OwnerFilter, { title: string; text: string }> = {
  all: { title: 'Вечеров пока нет', text: 'Создай первый — это пара минут' },
  draft: { title: 'Черновиков нет', text: 'Новый вечер начинается с черновика.' },
  past: { title: 'Прошедших вечеров пока нет', text: 'Здесь соберутся вечера, которые уже прошли.' },
};

/** «Мои вечера»: the owner's evenings with their status, and the way to a new one (spec §3.1). */
export function OwnerEvents() {
  const api = useOwnerApi();
  const navigate = useNavigate();
  const [filter, setFilter] = useState<OwnerFilter>('all');
  const events = useQuery({ queryKey: ['owner', 'events', filter], queryFn: () => api.events(filter) });
  const denied = events.error instanceof OwnerApiError && (events.error.status === 401 || events.error.status === 403);

  useMainButton(
    denied ? null : { text: '+ Новый вечер', enabled: true, progress: false, onClick: () => navigate('/owner/events/new') },
  );
  useBackButton(() => navigate('/me'));

  return (
    <main className={styles.page}>
      <h1 className={`t-h1 ${styles.title}`}>Мои вечера</h1>
      {events.isError ? (
        <OwnerLoadError error={events.error} onRetry={() => void events.refetch()} />
      ) : (
        <>
          <FilterChips
            label="Фильтр вечеров"
            items={FILTERS}
            value={filter === 'all' ? null : filter}
            onChange={(id) => setFilter((id ?? 'all') as OwnerFilter)}
          />
          {events.isPending ? (
            <div className={styles.list}>
              <Skeleton height={94} />
              <Skeleton height={94} />
              <Skeleton height={94} />
            </div>
          ) : events.data.length === 0 ? (
            <EmptyState {...EMPTY[filter]} />
          ) : (
            <ul className={styles.list}>
              {events.data.map((item) => (
                <li key={item.id}>
                  <Row item={item} past={filter === 'past'} />
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </main>
  );
}

function Row({ item, past }: { item: OwnerEventListItem; past: boolean }) {
  const status = ownerStatus(item, past);
  return (
    <Link to={`/owner/events/${item.id}`} className={`glass ${styles.row}`}>
      {item.poster ? (
        <img
          className={styles.thumb}
          src={item.poster.url}
          alt=""
          loading="lazy"
          style={{ objectPosition: `${Math.round(item.poster.focusX * 100)}% ${Math.round(item.poster.focusY * 100)}%` }}
        />
      ) : (
        <span className={`${styles.thumb} ${styles.noPhoto}`} data-testid="thumb-empty">
          нет фото
        </span>
      )}
      <span className={styles.body}>
        <span className={`t-h3 ${styles.name}`}>{item.title}</span>
        <span className={styles.when}>{formatDateTime(item.startsAt, CLUB_TIMEZONE)}</span>
        <Pill tone={status.tone}>{status.text}</Pill>
      </span>
    </Link>
  );
}
