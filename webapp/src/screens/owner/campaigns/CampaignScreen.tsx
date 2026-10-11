import { useQuery } from '@tanstack/react-query';
import { useParams, useSearchParams } from 'react-router-dom';
import { useRequiredCampaignApi } from '../../../api/campaigns/CampaignApiProvider';
import { CMSG } from '../../../api/campaigns/messages';
import { Skeleton } from '../../../ui/Skeleton';
import { OwnerLoadError } from '../OwnerLoadError';
import { CampaignEditor } from './CampaignEditor';
import { CampaignView } from './CampaignView';
import styles from '../OwnerEventForm.module.css';

const NOT_FOUND = { title: CMSG.campaignNotFound, text: 'Вернись к списку и открой рассылку оттуда.', to: '/owner/campaigns' };

/** Route entry: one screen per campaign, so a saved «new» starts clean at its own address. */
export function CampaignScreen() {
  const { id = 'new' } = useParams();
  const [params] = useSearchParams();
  const templateId = id === 'new' ? params.get('template') : null;
  return <Screen key={`${id}:${templateId ?? ''}`} id={id} templateId={templateId} />;
}

/** `new` and drafts or scheduled campaigns open in the editor; the rest are read only. */
function Screen({ id, templateId }: { id: string; templateId: string | null }) {
  const api = useRequiredCampaignApi();
  const isNew = id === 'new';
  const campaign = useQuery({ queryKey: ['campaigns', id], queryFn: () => api.campaign(id), enabled: !isNew });
  const templates = useQuery({
    queryKey: ['campaigns', 'templates'],
    queryFn: () => api.templates(),
    enabled: templateId !== null,
  });
  const error = isNew ? templates.error : campaign.error;
  const ready = isNew ? templateId === null || templates.data !== undefined : campaign.data !== undefined;

  if (!ready) {
    return (
      <main className={styles.page}>
        {error ? (
          <OwnerLoadError
            error={error}
            notFound={NOT_FOUND}
            onRetry={() => void (isNew ? templates.refetch() : campaign.refetch())}
          />
        ) : (
          <div className={styles.fields}>
            <Skeleton height={32} />
            <Skeleton height={76} />
            <Skeleton height={160} />
          </div>
        )}
      </main>
    );
  }
  if (isNew) {
    return <CampaignEditor campaign={null} template={templates.data?.find((t) => t.id === templateId) ?? null} />;
  }
  const c = campaign.data!;
  return c.status === 'draft' || c.status === 'scheduled' ? <CampaignEditor campaign={c} /> : <CampaignView campaign={c} />;
}
