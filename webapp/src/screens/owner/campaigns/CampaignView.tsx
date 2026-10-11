import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useRequiredCampaignApi } from '../../../api/campaigns/CampaignApiProvider';
import type { Campaign } from '../../../api/campaigns/types';
import { formatDateTime } from '../../../lib/format';
import { campaignStatus, groupFailures } from '../../../owner/campaigns/labels';
import { htmlToMarkup } from '../../../owner/campaigns/text';
import { CLUB_TIMEZONE } from '../../../owner/form';
import { useBackButton } from '../../../telegram/hooks';
import { Button } from '../../../ui/Button';
import { Dialog } from '../../../ui/Dialog';
import { Pill } from '../../../ui/Pill';
import { Skeleton } from '../../../ui/Skeleton';
import { OwnerLoadError } from '../OwnerLoadError';
import { MessageBubble } from './parts/MessageBubble';
import styles from './CampaignView.module.css';

/** A running or finished campaign: read-only message, delivery numbers, stop and repeat. */
export function CampaignView({ campaign: initial }: { campaign: Campaign }) {
  const api = useRequiredCampaignApi();
  const navigate = useNavigate();
  const client = useQueryClient();
  // Follows the cached copy, so a stop shows at once.
  const { data: campaign } = useQuery({
    queryKey: ['campaigns', initial.id],
    queryFn: () => api.campaign(initial.id),
    initialData: initial,
  });
  const [confirmStop, setConfirmStop] = useState(false);
  const status = campaignStatus(campaign);
  const running = campaign.status === 'running';
  const cancelled = campaign.status === 'cancelled';

  useBackButton(() => navigate('/owner/campaigns'));

  const stats = useQuery({
    queryKey: ['campaigns', campaign.id, 'stats'],
    queryFn: () => api.stats(campaign.id),
    enabled: !cancelled,
    refetchInterval: running ? 5000 : false,
  });

  const stop = useMutation({
    mutationFn: () => api.stop(campaign.id),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['campaigns'] }),
  });
  const repeat = useMutation({
    mutationFn: () => api.duplicate(campaign.id),
    onSuccess: (copy) => {
      void client.invalidateQueries({ queryKey: ['campaigns'] });
      navigate(`/owner/campaigns/${copy.id}`);
    },
  });

  const dates: string[] = [];
  if (campaign.scheduledAt && !campaign.startedAt) {
    dates.push(`Запланирована на ${formatDateTime(campaign.scheduledAt, CLUB_TIMEZONE)}`);
  }
  if (campaign.startedAt) dates.push(`Начата ${formatDateTime(campaign.startedAt, CLUB_TIMEZONE)}`);
  if (campaign.finishedAt) dates.push(`Закончена ${formatDateTime(campaign.finishedAt, CLUB_TIMEZONE)}`);

  const s = stats.data;
  return (
    <main className={styles.page}>
      <div className={styles.head}>
        <h1 className={`t-h1 ${styles.title}`}>{campaign.title}</h1>
        <Pill tone={status.tone}>{status.text}</Pill>
        {dates.length > 0 ? (
          <ul className={styles.dates}>
            {dates.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        ) : null}
      </div>

      <MessageBubble
        markup={htmlToMarkup(campaign.body)}
        imageUrl={campaign.image.kind === 'none' ? null : (campaign.image.url ?? null)}
        buttons={campaign.buttons}
      />

      {cancelled ? (
        <p className={styles.note}>Рассылка отменена — никто ничего не получил</p>
      ) : stats.isError ? (
        <OwnerLoadError error={stats.error} onRetry={() => void stats.refetch()} />
      ) : !s ? (
        <Skeleton height={160} />
      ) : (
        <dl className={`glass ${styles.stats}`} aria-label="Статистика">
          <Stat label="Получатели" value={s.recipients} />
          <Stat label="Доставлено" value={s.delivered} />
          <Stat label="Не доставлено" value={s.failed} />
          {s.failed > 0 ? (
            <ul className={styles.reasons}>
              {groupFailures(s.failedReasons).map((r) => (
                <li key={r.label}>{`${r.label} — ${r.count}`}</li>
              ))}
            </ul>
          ) : null}
          <Stat label="Пропущено из-за лимита" value={s.skippedLimit} />
          <Stat label="Нажали" value={s.clicked} />
          {s.anonymousClicks > 0 ? (
            <p className={styles.note}>{`и ещё ${s.anonymousClicks} ${clicksWord(s.anonymousClicks)} без входа`}</p>
          ) : null}
          {s.bought !== null ? <Stat label="Купили" value={s.bought} /> : null}
        </dl>
      )}

      <div className={styles.actions}>
        {running ? (
          <Button variant="secondary" wide onClick={() => setConfirmStop(true)}>
            Остановить
          </Button>
        ) : (
          <Button wide loading={repeat.isPending} disabled={repeat.isPending} onClick={() => repeat.mutate()}>
            Повторить
          </Button>
        )}
      </div>

      {confirmStop ? (
        <Dialog
          title="Остановить рассылку?"
          text="Кто ещё не получил — не получит."
          confirmLabel="Остановить"
          cancelLabel="Не останавливать"
          onConfirm={() => {
            setConfirmStop(false);
            stop.mutate();
          }}
          onCancel={() => setConfirmStop(false)}
        />
      ) : null}
    </main>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className={styles.stat}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function clicksWord(n: number): string {
  const last = n % 10;
  const tens = n % 100;
  if (last === 1 && tens !== 11) return 'нажатие';
  if (last >= 2 && last <= 4 && (tens < 12 || tens > 14)) return 'нажатия';
  return 'нажатий';
}
