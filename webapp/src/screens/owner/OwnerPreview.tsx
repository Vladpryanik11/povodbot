import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { useOwnerApi, useOwnerDrafts } from '../../api/owner/OwnerApiProvider';
import { emptyForm, formFromEvent, toPreviewDetail } from '../../owner/form';
import { Skeleton } from '../../ui/Skeleton';
import { EventScreen } from '../EventScreen';
import { OwnerLoadError } from './OwnerLoadError';
import styles from './OwnerEventForm.module.css';

/** «Как видит гость»: the guest's evening screen built from the owner's input, saved or not (spec §3.4). */
export function OwnerPreview() {
  const { id = 'new' } = useParams();
  const isNew = id === 'new';
  const api = useOwnerApi();
  const drafts = useOwnerDrafts();
  const event = useQuery({ queryKey: ['owner', 'event', id], queryFn: () => api.event(id), enabled: !isNew });

  // The poster and the sold seats come from the saved evening, so wait for it.
  if (!isNew && !event.data) {
    return (
      <main className={styles.page}>
        {event.isError ? (
          <OwnerLoadError error={event.error} onRetry={() => void event.refetch()} />
        ) : (
          <div className={styles.fields}>
            <Skeleton height={200} />
            <Skeleton height={120} />
          </div>
        )}
      </main>
    );
  }

  const form = drafts.get(id) ?? (event.data ? formFromEvent(event.data) : emptyForm());
  return <EventScreen preview={toPreviewDetail(form, event.data, Date.now())} />;
}
