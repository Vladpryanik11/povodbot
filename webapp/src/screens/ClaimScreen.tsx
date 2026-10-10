import { useQueryClient } from '@tanstack/react-query';
import { Gift, Link2Off } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useApi } from '../api/ApiProvider';
import { ApiError } from '../api/AppApi';
import type { Ticket } from '../api/types';
import { formatDateTime } from '../lib/format';
import { useMainButton } from '../telegram/hooks';
import { EmptyState } from '../ui/EmptyState';
import { ErrorState } from '../ui/ErrorState';
import { Skeleton } from '../ui/Skeleton';

type Result = { kind: 'ok'; ticket: Ticket } | { kind: 'taken' } | { kind: 'missing' } | { kind: 'network' };

/** A friend opens a shared ticket: it moves to them once; later attempts get an explanation. */
export function ClaimScreen() {
  const { token = '' } = useParams();
  const api = useApi();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [result, setResult] = useState<Result | null>(null);
  const started = useRef(false);

  const claim = () => {
    setResult(null);
    api
      .claimTicket(token)
      .then((ticket) => {
        void queryClient.invalidateQueries({ queryKey: ['tickets'] });
        setResult({ kind: 'ok', ticket });
      })
      .catch((error: unknown) => {
        const code = error instanceof ApiError ? error.code : 'network';
        setResult({ kind: code === 'already_claimed' ? 'taken' : code === 'not_found' ? 'missing' : 'network' });
      });
  };

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    claim();
    // The claim runs once per screen; retries go through the button.
  }, []);

  useMainButton(
    result?.kind === 'ok'
      ? { text: 'Открыть билет', enabled: true, progress: false, onClick: () => navigate(`/tickets/${result.ticket.id}`, { replace: true }) }
      : null,
  );

  if (!result) return <Skeleton height={200} />;
  if (result.kind === 'ok') {
    return (
      <EmptyState
        icon={Gift}
        title="Билет ваш"
        text={`${result.ticket.eventTitle}, ${formatDateTime(result.ticket.startsAt, result.ticket.timezone)}. Он уже во вкладке «Билеты».`}
      />
    );
  }
  if (result.kind === 'taken') {
    return (
      <EmptyState
        icon={Link2Off}
        title="Этот билет уже забрал другой гость"
        text="Попросите отправителя прислать новую ссылку."
        action={{ label: 'К афише', onClick: () => navigate('/', { replace: true }) }}
      />
    );
  }
  if (result.kind === 'missing') {
    return (
      <EmptyState
        icon={Link2Off}
        title="Ссылка не работает"
        text="Возможно, отправитель её отозвал."
        action={{ label: 'К афише', onClick: () => navigate('/', { replace: true }) }}
      />
    );
  }
  return (
    <ErrorState title="Нет связи" text="Проверьте интернет и попробуйте ещё раз." actionLabel="Повторить" onAction={claim} />
  );
}
