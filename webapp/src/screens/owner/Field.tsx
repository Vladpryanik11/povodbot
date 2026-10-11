import type { ReactNode } from 'react';
import styles from './OwnerEventForm.module.css';

export interface ControlProps {
  id: string;
  className: string;
  'aria-describedby'?: string;
  'aria-invalid'?: true;
}

/** A visible label over its control, and the error under it, tied by aria-describedby. */
export function Field({
  id,
  label,
  error,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  children(control: ControlProps): ReactNode;
}) {
  const errorId = `${id}-error`;
  return (
    <div className={styles.field}>
      <label htmlFor={id} className={styles.label}>
        {label}
      </label>
      {children({
        id,
        className: styles.input,
        'aria-describedby': error ? errorId : undefined,
        'aria-invalid': error ? true : undefined,
      })}
      {error ? (
        <p id={errorId} className={styles.error}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
