import { ArrowLeft } from 'lucide-react';
import type { DirectionIcon, Poster as PosterData } from '../api/types';
import { ICON_STROKE } from './icons';
import { Poster } from './Poster';
import styles from './PhotoHeader.module.css';

interface PhotoHeaderProps {
  poster: PosterData | null;
  title: string;
  icon: DirectionIcon;
  /** Pass only outside Telegram; inside, the native back button is used. */
  onBack?: () => void;
}

export function PhotoHeader({ poster, title, icon, onBack }: PhotoHeaderProps) {
  return (
    <div className={styles.header}>
      <Poster poster={poster} title={title} ratio="2:1" icon={icon} className={styles.poster} />
      {onBack ? (
        <button type="button" className={styles.back} aria-label="Назад" onClick={onBack}>
          <ArrowLeft size={20} strokeWidth={ICON_STROKE} aria-hidden="true" />
        </button>
      ) : null}
    </div>
  );
}
