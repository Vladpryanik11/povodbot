import type { DirectionIcon, Poster } from '../api/types';
import { DIRECTION_ICONS, ICON_STROKE } from './icons';
import styles from './PosterImage.module.css';

const MIN_SHORT_SIDE = 600;

/** A photo smaller than 600 px on the short side would look soft at full width; it gets the colour block. */
export function usablePhoto(poster: Poster | null): poster is Poster {
  return poster !== null && Math.min(poster.width, poster.height) >= MIN_SHORT_SIDE;
}

/** Fills its box: the photo at the owner's focus point, or a block of the poster colour with the direction icon. */
export function PosterImage({ poster, color, icon }: { poster: Poster | null; color: string; icon: DirectionIcon }) {
  if (usablePhoto(poster)) {
    return (
      <img
        className={styles.img}
        src={poster.url}
        alt=""
        aria-hidden="true"
        loading="lazy"
        style={{ objectPosition: `${Math.round(poster.focusX * 100)}% ${Math.round(poster.focusY * 100)}%` }}
      />
    );
  }
  const Icon = DIRECTION_ICONS[icon];
  return (
    <div className={styles.block} style={{ backgroundColor: color }} data-testid="poster-fallback">
      <Icon size={72} strokeWidth={ICON_STROKE} aria-hidden="true" />
    </div>
  );
}
