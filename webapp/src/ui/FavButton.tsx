import { useFavorites } from '../lib/favorites';
import { useTg } from '../telegram/hooks';
import { HeartIcon } from './icons/NavIcons';
import styles from './FavButton.module.css';

/** Glass heart on a poster; stops the tap from opening the card underneath. */
export function FavButton({ eventId, size = 36 }: { eventId: string; size?: 36 | 40 }) {
  const tg = useTg();
  const { has, toggle } = useFavorites();
  const saved = has(eventId);
  return (
    <button
      type="button"
      className={`${styles.fav} glass`}
      style={{ width: size, height: size }}
      aria-pressed={saved}
      aria-label={saved ? 'Убрать из избранного' : 'В избранное'}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        tg.haptic.impact('light');
        toggle(eventId);
      }}
    >
      <HeartIcon filled={saved} />
    </button>
  );
}
