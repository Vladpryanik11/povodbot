import { useQuery } from '@tanstack/react-query';
import { Vote } from 'lucide-react';
import { useApi } from '../api/ApiProvider';
import { usePollVote } from '../polls/usePollVote';
import { EmptyState } from '../ui/EmptyState';
import { ErrorState } from '../ui/ErrorState';
import { PollCard } from '../ui/PollCard';
import { Skeleton } from '../ui/Skeleton';
import styles from './Polls.module.css';

export function Polls() {
  const api = useApi();
  const polls = useQuery({ queryKey: ['polls'], queryFn: () => api.polls() });
  const { vote, closedNow, failed, pending } = usePollVote();

  if (polls.isError) {
    return (
      <ErrorState
        title="Нет связи"
        text="Проверь интернет и попробуй ещё раз."
        actionLabel="Повторить"
        onAction={() => void polls.refetch()}
      />
    );
  }
  if (!polls.data) {
    return (
      <div className={styles.page}>
        <Skeleton height={180} />
      </div>
    );
  }
  if (polls.data.length === 0) {
    return (
      <EmptyState icon={Vote} title="Сейчас ничего не выбираем" text="Новое голосование появится — напишем в боте." />
    );
  }

  const active = polls.data.filter((p) => !p.closed);
  const closed = polls.data.filter((p) => p.closed);
  return (
    <main className={styles.page}>
      <h1 className={`t-h1 ${styles.title}`}>Голосуем</h1>
      {active.map((poll) => (
        <PollCard
          key={poll.id}
          poll={poll}
          closedNow={closedNow.has(poll.id)}
          failed={failed.has(poll.id)}
          busy={pending === poll.id}
          onVote={(optionId) => void vote(poll, optionId)}
        />
      ))}
      {closed.length ? (
        <>
          <h2 className={`t-h3 ${styles.subtitle}`}>Итоги</h2>
          {closed.map((poll) => (
            <PollCard key={poll.id} poll={poll} onVote={() => undefined} />
          ))}
        </>
      ) : null}
    </main>
  );
}
