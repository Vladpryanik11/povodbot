import { useTg } from '../telegram/hooks';
import styles from './FilterChips.module.css';

type Item = { id: string; title: string };

interface Props {
  items: Item[];
  value: string | null;
  onChange(id: string | null): void;
  /** Accessible name of the group. */
  label?: string;
}

/** Chip filter, directions by default: «Все» is null; the chosen chip is white with black text. */
export function FilterChips({ items, value, onChange, label = 'Направления' }: Props) {
  const tg = useTg();
  const all: { id: string | null; title: string }[] = [{ id: null, title: 'Все' }, ...items];
  return (
    <div className={styles.row} role="radiogroup" aria-label={label}>
      {all.map((item) => {
        const checked = item.id === value;
        return (
          <button
            key={item.id ?? 'all'}
            type="button"
            role="radio"
            aria-checked={checked}
            className={`${styles.chip} ${checked ? styles.on : 'glass'}`}
            onClick={() => {
              tg.haptic.selection();
              onChange(item.id);
            }}
          >
            {item.title}
          </button>
        );
      })}
    </div>
  );
}
