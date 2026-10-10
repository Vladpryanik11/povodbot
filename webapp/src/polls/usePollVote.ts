import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useApi } from '../api/ApiProvider';
import { ApiError } from '../api/AppApi';
import type { EventDetail, Poll } from '../api/types';
import { useTg } from '../telegram/hooks';

/** Votes and keeps every cached copy of the poll (polls tab, event card) in step. */
export function usePollVote() {
  const api = useApi();
  const tg = useTg();
  const queryClient = useQueryClient();
  const [closedNow, setClosedNow] = useState<ReadonlySet<string>>(new Set());
  const [pending, setPending] = useState<string | null>(null);
  const [failed, setFailed] = useState<ReadonlySet<string>>(new Set());

  const vote = async (poll: Poll, optionId: string) => {
    if (pending) return;
    tg.haptic.selection();
    setPending(poll.id);
    setFailed((ids) => {
      const next = new Set(ids);
      next.delete(poll.id);
      return next;
    });
    try {
      const updated = await api.vote(poll.id, optionId);
      queryClient.setQueryData<Poll[]>(['polls'], (old) => old?.map((p) => (p.id === updated.id ? updated : p)));
      queryClient.setQueriesData<EventDetail>({ queryKey: ['event'] }, (old) =>
        old && old.poll?.id === updated.id ? { ...old, poll: updated } : old,
      );
    } catch (error) {
      if (error instanceof ApiError && error.code === 'poll_closed') {
        setClosedNow((ids) => new Set(ids).add(poll.id));
      } else {
        tg.haptic.notify('error');
        setFailed((ids) => new Set(ids).add(poll.id));
      }
    } finally {
      setPending(null);
    }
  };

  return { vote, closedNow, failed, pending };
}
