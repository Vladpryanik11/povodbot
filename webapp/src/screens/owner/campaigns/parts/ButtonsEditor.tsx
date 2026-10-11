import type { CampaignButton } from '../../../../api/campaigns/types';
import { MAX_BUTTONS } from '../../../../owner/campaigns/rules';
import { Button } from '../../../../ui/Button';
import formStyles from '../../OwnerEventForm.module.css';
import styles from './parts.module.css';

interface Props {
  buttons: CampaignButton[];
  onChange(next: CampaignButton[]): void;
  hasEvent: boolean;
  error?: string;
}

/** Up to two buttons under the message: the evening's page or a link. */
export function ButtonsEditor({ buttons, onChange, hasEvent, error }: Props) {
  const set = (i: number, button: CampaignButton) => onChange(buttons.map((b, j) => (j === i ? button : b)));
  const add = () =>
    onChange([
      ...buttons,
      hasEvent ? { kind: 'event', label: 'Открыть вечер' } : { kind: 'url', label: '', url: 'https://' },
    ]);
  return (
    <fieldset className={formStyles.tickets} aria-describedby={error ? 'buttons-error' : undefined}>
      <legend className={formStyles.label}>Кнопки</legend>
      {buttons.map((button, i) => (
        <div key={i} className={`glass ${styles.button}`}>
          <div className={formStyles.field}>
            <label htmlFor={`button-${i}-kind`} className={formStyles.label}>
              Что открывает
            </label>
            <select
              id={`button-${i}-kind`}
              className={formStyles.input}
              value={button.kind}
              onChange={(e) =>
                set(
                  i,
                  e.target.value === 'event'
                    ? { kind: 'event', label: button.label || 'Открыть вечер' }
                    : { kind: 'url', label: button.label, url: 'https://' },
                )
              }
            >
              <option value="event" disabled={!hasEvent}>
                Открыть вечер
              </option>
              <option value="url">Ссылка</option>
            </select>
          </div>
          <div className={formStyles.field}>
            <label htmlFor={`button-${i}-label`} className={formStyles.label}>
              Подпись
            </label>
            <input
              id={`button-${i}-label`}
              className={formStyles.input}
              value={button.label}
              onChange={(e) => set(i, { ...button, label: e.target.value })}
            />
          </div>
          {button.kind === 'url' ? (
            <div className={formStyles.field}>
              <label htmlFor={`button-${i}-url`} className={formStyles.label}>
                Адрес
              </label>
              <input
                id={`button-${i}-url`}
                className={formStyles.input}
                type="url"
                inputMode="url"
                value={button.url}
                onChange={(e) => set(i, { ...button, url: e.target.value })}
              />
            </div>
          ) : null}
          <Button
            variant="link"
            className={formStyles.remove}
            onClick={() => onChange(buttons.filter((_, j) => j !== i))}
          >
            Убрать
          </Button>
        </div>
      ))}
      {buttons.length < MAX_BUTTONS ? (
        <Button variant="secondary" wide onClick={add}>
          + Кнопка
        </Button>
      ) : null}
      {error ? (
        <p id="buttons-error" className={formStyles.error}>
          {error}
        </p>
      ) : null}
    </fieldset>
  );
}
