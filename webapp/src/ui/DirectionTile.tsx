import type { Direction } from '../api/types';
import { DIRECTION_ICONS, ICON_STROKE } from './icons';
import styles from './DirectionTile.module.css';

interface DirectionTileProps {
  direction: Pick<Direction, 'title' | 'icon'>;
  selected: boolean;
  onSelect: () => void;
}

export function DirectionTile({ direction, selected, onSelect }: DirectionTileProps) {
  const Icon = DIRECTION_ICONS[direction.icon];
  return (
    <button type="button" className={`${styles.tile} ${selected ? styles.selected : ''}`} aria-pressed={selected} onClick={onSelect}>
      <span className={styles.icon}>
        <Icon size={24} strokeWidth={ICON_STROKE} aria-hidden="true" />
      </span>
      {direction.title}
    </button>
  );
}
