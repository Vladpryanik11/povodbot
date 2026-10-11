import type { AudienceFilter, AudienceRelation, PurchaseFilter } from '../../../../api/campaigns/types';
import type { OwnerDirection } from '../../../../api/owner/types';
import { guestsLabel, PURCHASE_LABEL, RELATION_LABEL } from '../../../../owner/campaigns/labels';
import { Toggle } from '../../../../ui/Toggle';
import formStyles from '../../OwnerEventForm.module.css';
import styles from './parts.module.css';

export interface AudienceCountState {
  count: number | null;
  overLimit: number;
  pending: boolean;
}

interface Props {
  value: AudienceFilter;
  onChange(next: AudienceFilter): void;
  /** Published and past evenings. */
  events: { id: string; title: string }[];
  directions: OwnerDirection[];
  audience: AudienceCountState;
  error?: string;
}

/** Who gets the message, and how many of them. */
export function AudienceEditor({ value, onChange, events, directions, audience, error }: Props) {
  const event = value.event;
  return (
    <fieldset className={formStyles.tickets}>
      <legend className={formStyles.label}>Кому</legend>
      <div className={formStyles.switchRow}>
        <span>Связь с вечером</span>
        <Toggle
          label="Связь с вечером"
          checked={event !== null}
          disabled={events.length === 0}
          onChange={(on) => onChange({ ...value, event: on ? { id: events[0].id, relation: 'going' } : null })}
        />
      </div>
      {event ? (
        <>
          <div className={formStyles.field}>
            <label htmlFor="audience-event" className={formStyles.label}>
              Вечер
            </label>
            <select
              id="audience-event"
              className={formStyles.input}
              value={event.id}
              onChange={(e) => onChange({ ...value, event: { ...event, id: e.target.value } })}
            >
              {events.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.title}
                </option>
              ))}
            </select>
          </div>
          <div className={formStyles.field}>
            <label htmlFor="audience-relation" className={formStyles.label}>
              Кто
            </label>
            <select
              id="audience-relation"
              className={formStyles.input}
              value={event.relation}
              onChange={(e) =>
                onChange({ ...value, event: { ...event, relation: e.target.value as AudienceRelation } })
              }
            >
              {Object.entries(RELATION_LABEL).map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        </>
      ) : null}
      <div className={formStyles.field}>
        <label htmlFor="audience-direction" className={formStyles.label}>
          Направление
        </label>
        <select
          id="audience-direction"
          className={formStyles.input}
          value={value.directionId ?? ''}
          onChange={(e) => onChange({ ...value, directionId: e.target.value || null })}
        >
          <option value="">Любое</option>
          {directions.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
      </div>
      <div className={formStyles.field}>
        <label htmlFor="audience-purchases" className={formStyles.label}>
          Покупки
        </label>
        <select
          id="audience-purchases"
          className={formStyles.input}
          value={value.purchases}
          onChange={(e) => onChange({ ...value, purchases: e.target.value as PurchaseFilter })}
        >
          {Object.entries(PURCHASE_LABEL).map(([id, label]) => (
            <option key={id} value={id}>
              {label}
            </option>
          ))}
        </select>
      </div>
      <p className={styles.count} aria-live="polite">
        {audience.count === null ? 'Считаем получателей…' : `Получат ${guestsLabel(audience.count)}`}
      </p>
      {audience.overLimit > 0 ? (
        <p className={styles.note}>{`Ещё ${audience.overLimit} уже получили 2 рассылки за неделю — им не придёт`}</p>
      ) : null}
      {error ? <p className={formStyles.error}>{error}</p> : null}
    </fieldset>
  );
}
