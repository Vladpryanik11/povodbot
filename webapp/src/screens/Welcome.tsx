import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useApi } from '../api/ApiProvider';
import { useDirections } from '../api/useDirections';
import { billboardSubtitle } from '../lib/format';
import { useMainButton } from '../telegram/hooks';
import { useGlow } from '../ui/Glow';
import { PosterImage } from '../ui/PosterImage';
import { useEventColor } from '../ui/useEventColor';
import styles from './Welcome.module.css';

/** The club is 18+; events carry no age field yet. */
const AGE = '18+';

/**
 * Shown once: the nearest evening as a full-screen billboard with its glow, the greeting over it, «Заходим» below
 * (spec v2 §5). The owner will add the consent wording into the owner slot later (spec §13).
 */
export function Welcome({ onAccept }: { onAccept: () => Promise<void> }) {
  const api = useApi();
  const directions = useDirections();
  const events = useQuery({ queryKey: ['events', 'all'], queryFn: () => api.events() });
  const nearest = events.data?.length ? [...events.data].sort((a, b) => a.startsAt.localeCompare(b.startsAt))[0] : null;
  const direction = directions.find((d) => d.id === nearest?.directionId);
  const color = useEventColor(nearest);
  useGlow(color);

  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  useMainButton({
    text: 'Заходим',
    enabled: !busy,
    progress: busy,
    onClick: () => {
      if (busy) return;
      setBusy(true);
      setFailed(false);
      onAccept().catch(() => {
        setBusy(false);
        setFailed(true);
      });
    },
  });

  return (
    <main className={styles.screen}>
      {nearest ? (
        <div className={styles.backdrop}>
          <PosterImage poster={nearest.poster} color={color ?? '#000000'} icon={direction?.icon ?? 'film'} />
          <div className={styles.scrim} />
          <div className={styles.event}>
            <span className={styles.meta}>{direction ? `${direction.title} · ${AGE}` : AGE}</span>
            <p className={`t-h2 ${styles.eventTitle}`}>{nearest.title}</p>
            <p className={styles.subtitle}>{billboardSubtitle(nearest.startsAt, nearest.timezone, Date.now())}</p>
          </div>
        </div>
      ) : null}
      <div className={styles.copy}>
        <h1 className={`t-billboard ${styles.title}`}>Привет, это «Повод»</h1>
        <p className={styles.text}>
          Маленький клуб в Москве: киновечера, мастерклассы и книжный клуб для своих. Выбирай вечер, бери билет — и
          увидимся.
        </p>
        <p className={styles.owner} data-slot="owner-consent" />
        {failed ? (
          <p className={styles.error} role="alert">
            Не получилось. Проверь интернет и попробуй ещё раз.
          </p>
        ) : null}
      </div>
    </main>
  );
}
