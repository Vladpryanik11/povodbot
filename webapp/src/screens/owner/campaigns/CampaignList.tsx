import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useRequiredCampaignApi } from '../../../api/campaigns/CampaignApiProvider';
import type { CampaignFilter, CampaignListItem } from '../../../api/campaigns/types';
import { OwnerApiError } from '../../../api/owner/OwnerApi';
import { formatDateTime } from '../../../lib/format';
import { campaignStatus, guestsLabel } from '../../../owner/campaigns/labels';
import { CLUB_TIMEZONE } from '../../../owner/form';
import { useBackButton, useMainButton } from '../../../telegram/hooks';
import { EmptyState } from '../../../ui/EmptyState';
import { FilterChips } from '../../../ui/FilterChips';
import { Pill } from '../../../ui/Pill';
import { Skeleton } from '../../../ui/Skeleton';
import { OwnerLoadError } from '../OwnerLoadError';
import { OwnerTabs } from '../OwnerTabs';
import styles from './campaigns.module.css';

const FILTERS: { id: CampaignFilter; title: string }[] = [
  { id: 'draft', title: 'Черновики' },
  { id: 'scheduled', title: 'Запланированы' },
  { id: 'sent', title: 'Отправлены' },
];

const EMPTY: Record<CampaignFilter, { title: string; text: string }> = {
  draft: { title: 'Черновиков нет', text: 'Новая рассылка начинается с черновика.' },
  scheduled: { title: 'Запланированных нет', text: 'Назначь время — рассылка уйдёт сама.' },
  sent: { title: 'Отправленных пока нет', text: 'Здесь будут рассылки и то, как их встретили.' },
};

/** «Рассылки»: drafts, scheduled and sent campaigns, and the way to a new one (spec §4). */
export function CampaignList() {
  const api = useRequiredCampaignApi();
  const navigate = useNavigate();
  const [filter, setFilter] = useState<CampaignFilter>('draft');
  const campaigns = useQuery({ queryKey: ['campaigns', 'list', filter], queryFn: () => api.campaigns(filter) });
  const denied =
    campaigns.error instanceof OwnerApiError && (campaigns.error.status === 401 || campaigns.error.status === 403);

  useMainButton(
    denied
      ? null
      : { text: '+ Новая рассылка', enabled: true, progress: false, onClick: () => navigate('/owner/campaigns/start') },
  );
  useBackButton(() => navigate('/me'));

  return (
    <main className={styles.page}>
      <OwnerTabs current="campaigns" />
      <div className={styles.head}>
        <h1 className={`t-h1 ${styles.title}`}>Рассылки</h1>
        {denied ? null : (
          <Link to="/owner/campaigns/templates" className={`glass ${styles.headLink}`}>
            Шаблоны
          </Link>
        )}
      </div>
      {campaigns.isError ? (
        <OwnerLoadError error={campaigns.error} onRetry={() => void campaigns.refetch()} />
      ) : (
        <>
          <FilterChips
            label="Фильтр рассылок"
            items={FILTERS}
            value={filter}
            allTitle={null}
            onChange={(id) => setFilter((id ?? 'draft') as CampaignFilter)}
          />
          {campaigns.isPending ? (
            <div className={styles.list}>
              <Skeleton height={86} />
              <Skeleton height={86} />
              <Skeleton height={86} />
            </div>
          ) : campaigns.data.length === 0 ? (
            <EmptyState {...EMPTY[filter]} />
          ) : (
            <ul className={styles.list}>
              {campaigns.data.map((item) => (
                <li key={item.id}>
                  <Row item={item} />
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </main>
  );
}

function Row({ item }: { item: CampaignListItem }) {
  const status = campaignStatus(item);
  // A scheduled one carries its time in the pill.
  const when = item.startedAt ?? (item.status === 'scheduled' ? null : item.scheduledAt);
  return (
    <Link to={`/owner/campaigns/${item.id}`} className={`glass ${styles.row}`}>
      <span className={`t-h3 ${styles.name}`}>{item.title}</span>
      {when || item.recipientCount !== null ? (
        <span className={styles.meta}>
          {when ? <span>{formatDateTime(when, CLUB_TIMEZONE)}</span> : null}
          {item.recipientCount !== null ? <span>{guestsLabel(item.recipientCount)}</span> : null}
          {item.startedAt ? <span>{`доставлено ${item.delivered} · нажали ${item.clicked}`}</span> : null}
        </span>
      ) : null}
      <Pill tone={status.tone}>{status.text}</Pill>
    </Link>
  );
}
