import { Check } from 'lucide-react';
import type { Poll } from '../api/types';
import { formatDate, formatTime } from '../lib/format';
import { ICON_STROKE } from './icons';
import styles from './PollCard.module.css';

interface PollCardProps {
  poll: Poll;
  onVote: (optionId: string) => void;
  /** The server said it closed after the list was loaded. */
  closedNow?: boolean;
  busy?: boolean;
  /** The last vote did not reach the server. */
  failed?: boolean;
}

export function PollCard({ poll, onVote, closedNow = false, busy = false, failed = false }: PollCardProps) {
  const closed = poll.closed || closedNow;
  const deadline = `${formatDate(poll.closesAt, poll.timezone)}, ${formatTime(poll.closesAt, poll.timezone)}`;
  const mine = poll.options.find((o) => o.id === poll.myOptionId);
  return (
    <section className={`glass ${styles.card}`} aria-label={poll.question}>
      <h3 className={`t-h3 ${styles.question}`}>{poll.question}</h3>
      <p className={styles.meta}>{poll.closed ? 'Голосование закрыто' : `Проголосовало ${poll.votes}`}</p>
      <ul className={styles.options}>
        {poll.options.map((option) => {
          const chosen = option.id === poll.myOptionId;
          return (
            <li key={option.id}>
              <button
                type="button"
                className={`${styles.option} ${chosen ? styles.chosen : ''}`}
                aria-pressed={chosen}
                disabled={closed || busy}
                onClick={() => onVote(option.id)}
              >
                {option.percent !== null ? (
                  <span className={styles.bar} style={{ width: `${option.percent}%` }} aria-hidden="true" />
                ) : null}
                <span className={styles.label}>
                  {chosen ? <Check size={16} strokeWidth={ICON_STROKE + 0.5} aria-hidden="true" /> : null}
                  {option.title}
                </span>
                {option.percent !== null ? <span className={styles.percent}>{option.percent}%</span> : null}
              </button>
            </li>
          );
        })}
      </ul>
      {failed ? (
        <p className={styles.error} role="alert">
          Не получилось проголосовать. Попробуйте ещё раз.
        </p>
      ) : null}
      {closedNow && !poll.closed ? (
        <p className={styles.note} role="status">
          <strong>Голосование уже закрыто</strong>
          {mine ? <span>{` Ваш голос остался прежним: «${mine.title}».`}</span> : null}
        </p>
      ) : !closed && mine ? (
        <p className={styles.note}>Ваш голос учтён. Можно передумать до {deadline}</p>
      ) : null}
    </section>
  );
}
