import { useState } from 'react';
import { POSTER_COLORS } from '../lib/posterColor';
import { useMainButton } from '../telegram/hooks';
import { DIRECTION_ICONS, ICON_STROKE } from '../ui/icons';
import styles from './Welcome.module.css';

const TILES = [
  { icon: 'film', color: POSTER_COLORS[1] },
  { icon: 'dice', color: POSTER_COLORS[2] },
  { icon: 'talk', color: POSTER_COLORS[0] },
  { icon: 'party', color: POSTER_COLORS[5] },
] as const;

/** Shown once. The owner will add the consent wording into the owner slot later (spec §2). */
export function Welcome({ onAccept }: { onAccept: () => Promise<void> }) {
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
      <div className={styles.tiles} aria-hidden="true">
        {TILES.map(({ icon, color }) => {
          const Icon = DIRECTION_ICONS[icon];
          return (
            <span key={icon} className={styles.tile} style={{ backgroundColor: color }}>
              <Icon size={24} strokeWidth={ICON_STROKE} />
            </span>
          );
        })}
      </div>
      <p className={`t-billboard ${styles.brand}`}>Повод</p>
      <h1 className={`t-h1 ${styles.title}`}>Привет, это «Повод»</h1>
      <p className={styles.text}>
        Маленький клуб в Москве: киновечера, настолки, разговоры и вечеринки для своих. Здесь выбирают вечер, берут
        билет и голосуют, что смотрим и во что играем.
      </p>
      <p className={styles.owner} data-slot="owner-consent" />
      {failed ? (
        <p className={styles.error} role="alert">
          Не получилось. Проверьте интернет и попробуйте ещё раз.
        </p>
      ) : null}
    </main>
  );
}
