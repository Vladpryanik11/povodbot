import { useNavigate } from 'react-router-dom';
import { MSG } from '../../api/owner/messages';
import { OwnerApiError } from '../../api/owner/OwnerApi';
import { EmptyState } from '../../ui/EmptyState';
import { ErrorState } from '../../ui/ErrorState';

/** What an owner screen shows when its data does not load: no access, no such evening, or no network. */
interface NotFound {
  title: string;
  text: string;
  to: string;
}

const EVENT_NOT_FOUND: NotFound = {
  title: 'Вечер не найден',
  text: 'Вернись к списку и открой вечер оттуда.',
  to: '/owner',
};

export function OwnerLoadError({
  error,
  onRetry,
  notFound = EVENT_NOT_FOUND,
}: {
  error: unknown;
  onRetry(): void;
  notFound?: NotFound;
}) {
  const navigate = useNavigate();
  const known = error instanceof OwnerApiError ? error : null;
  if (known && (known.status === 401 || known.status === 403)) {
    return <EmptyState title="Нет доступа" text={known.message} />;
  }
  if (known?.status === 404) {
    return (
      <EmptyState
        title={notFound.title}
        text={notFound.text}
        action={{ label: 'К списку', onClick: () => navigate(notFound.to) }}
      />
    );
  }
  return <ErrorState title="Нет связи" text={known?.message ?? MSG.unknown} actionLabel="Повторить" onAction={onRetry} />;
}
