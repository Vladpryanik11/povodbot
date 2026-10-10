import { Minus, Plus } from 'lucide-react';
import { ticketsLabel } from '../lib/format';
import styles from './Stepper.module.css';
import { ICON_STROKE } from './icons';

interface StepperProps {
  value: number;
  min?: number;
  max: number;
  label: string;
  onChange: (value: number) => void;
}

export function Stepper({ value, min = 0, max, label, onChange }: StepperProps) {
  const spoken = `${label}: ${ticketsLabel(value)}`;
  const atMax = value >= max;
  return (
    <div className={styles.root}>
      <div className={styles.control}>
        <button
          type="button"
          className={styles.step}
          aria-label={`${spoken}. Убавить`}
          disabled={value <= min}
          onClick={() => onChange(value - 1)}
        >
          <Minus size={20} strokeWidth={ICON_STROKE} aria-hidden="true" />
        </button>
        <span className={styles.value} aria-hidden="true">
          {value}
        </span>
        <button
          type="button"
          className={styles.step}
          aria-label={`${spoken}. Добавить`}
          disabled={atMax}
          onClick={() => onChange(value + 1)}
        >
          <Plus size={20} strokeWidth={ICON_STROKE} aria-hidden="true" />
        </button>
      </div>
      {atMax && max > 0 ? <span className={styles.limit}>Больше нет</span> : null}
    </div>
  );
}
