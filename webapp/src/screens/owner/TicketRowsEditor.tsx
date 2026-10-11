import { useId } from 'react';
import { newTicketRow, type TicketRow } from '../../owner/form';
import { Button } from '../../ui/Button';
import { Toggle } from '../../ui/Toggle';
import styles from './OwnerEventForm.module.css';

interface Props {
  rows: TicketRow[];
  error?: string;
  onChange(rows: TicketRow[]): void;
}

/**
 * Ticket types of the evening. A row not saved yet can be removed; a saved one can only be
 * taken off sale, because guests may already hold it.
 */
export function TicketRowsEditor({ rows, error, onChange }: Props) {
  const base = useId();
  const errorId = `${base}-error`;
  const patch = (key: string, change: Partial<TicketRow>) =>
    onChange(rows.map((row) => (row.key === key ? { ...row, ...change } : row)));

  return (
    <fieldset className={styles.tickets} aria-describedby={error ? errorId : undefined}>
      <legend className={styles.label}>Билеты</legend>
      {rows.map((row, index) => {
        const n = index + 1;
        const id = `${base}-${row.key}`;
        return (
          <div key={row.key} className={`glass ${styles.ticket}`}>
            <div className={styles.field}>
              <label htmlFor={`${id}-name`} className={styles.label}>
                Название билета
              </label>
              <input
                id={`${id}-name`}
                className={styles.input}
                aria-label={`Название билета ${n}`}
                value={row.name}
                onChange={(e) => patch(row.key, { name: e.target.value })}
              />
            </div>
            <div className={styles.pair}>
              <div className={styles.field}>
                <label htmlFor={`${id}-price`} className={styles.label}>
                  Цена, ₽
                </label>
                <input
                  id={`${id}-price`}
                  className={styles.input}
                  aria-label={`Цена билета ${n}, ₽`}
                  inputMode="decimal"
                  autoComplete="off"
                  value={row.price}
                  onChange={(e) => patch(row.key, { price: e.target.value })}
                />
              </div>
              <div className={styles.field}>
                <label htmlFor={`${id}-limit`} className={styles.label}>
                  Сколько билетов
                </label>
                <input
                  id={`${id}-limit`}
                  className={styles.input}
                  aria-label={`Сколько билетов ${n}`}
                  inputMode="numeric"
                  autoComplete="off"
                  value={row.limit}
                  onChange={(e) => patch(row.key, { limit: e.target.value })}
                />
              </div>
            </div>
            {row.id === null ? (
              <Button
                variant="link"
                className={styles.remove}
                aria-label={`Убрать билет ${n}`}
                onClick={() => onChange(rows.filter((r) => r.key !== row.key))}
              >
                Убрать
              </Button>
            ) : (
              <div className={styles.switchRow}>
                <span aria-hidden="true">В продаже</span>
                <Toggle
                  label={`В продаже, билет ${n}`}
                  checked={row.active}
                  onChange={(active) => patch(row.key, { active })}
                />
              </div>
            )}
          </div>
        );
      })}
      <Button variant="secondary" wide onClick={() => onChange([...rows, newTicketRow()])}>
        Добавить билет
      </Button>
      {error ? (
        <p id={errorId} className={styles.error}>
          {error}
        </p>
      ) : null}
    </fieldset>
  );
}
