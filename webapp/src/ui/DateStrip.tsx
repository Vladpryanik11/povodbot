import { dayKey, shortDay } from '../lib/format';
import styles from './DateStrip.module.css';

const DAY_MS = 24 * 60 * 60 * 1000;

type Props = {
  from: number;
  days: number;
  marked: Set<string>;
  value: string | null;
  onChange(key: string | null): void;
  timeZone?: string;
};

/** Two weeks of day pills; a dot over days with an evening, a second tap on the chosen day clears it. */
export function DateStrip({ from, days, marked, value, onChange, timeZone = 'Europe/Moscow' }: Props) {
  const keys = Array.from({ length: days }, (_, i) => dayKey(new Date(from + i * DAY_MS).toISOString(), timeZone));
  return (
    <div className={styles.row} role="group" aria-label="Дни">
      {keys.map((key) => {
        const { dow, day } = shortDay(key);
        const chosen = key === value;
        return (
          <button
            key={key}
            type="button"
            aria-pressed={chosen}
            data-marked={marked.has(key) || undefined}
            className={`${styles.day} ${chosen ? styles.on : ''}`}
            onClick={() => onChange(chosen ? null : key)}
          >
            <span className={styles.dow}>{dow}</span> <span className={styles.num}>{day}</span>
          </button>
        );
      })}
    </div>
  );
}
