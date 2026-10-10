import type { ReactNode } from 'react';
import type { DirectionIcon, Poster as PosterData } from '../api/types';
import { posterColor } from '../lib/posterColor';
import { DIRECTION_ICONS, ICON_STROKE } from './icons';
import { usablePhoto } from './PosterImage';
import styles from './Poster.module.css';

const RATIO_CLASS = { '4:5': styles.r45, '2:1': styles.r21, '3:1': styles.r31 } as const;


interface PosterProps {
  poster: PosterData | null;
  title: string;
  ratio: keyof typeof RATIO_CLASS;
  icon: DirectionIcon;
  className?: string;
  children?: ReactNode;
}

/** A photo under a scrim, or a coloured block when the photo is missing or too small. */
export function Poster({ poster, title, ratio, icon, className, children }: PosterProps) {
  const photo = usablePhoto(poster);
  const Icon = DIRECTION_ICONS[icon];
  return (
    <div
      data-testid="poster"
      className={`${styles.poster} ${RATIO_CLASS[ratio]} ${className ?? ''}`}
      style={photo ? undefined : { backgroundColor: posterColor(title) }}
    >
      {photo ? (
        <>
          <img
            className={styles.img}
            src={poster.url}
            alt=""
            aria-hidden="true"
            loading="lazy"
            style={{ objectPosition: `${Math.round(poster.focusX * 100)}% ${Math.round(poster.focusY * 100)}%` }}
          />
          <div className={styles.scrimTop} />
          <div className={styles.scrim} data-testid="scrim" />
        </>
      ) : (
        <Icon className={styles.fallbackIcon} size={96} strokeWidth={ICON_STROKE} aria-hidden="true" />
      )}
      {children ? <div className={styles.content}>{children}</div> : null}
    </div>
  );
}
