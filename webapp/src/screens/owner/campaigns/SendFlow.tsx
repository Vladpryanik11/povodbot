import { useRef, useState } from 'react';
import { QuietHoursError } from '../../../api/campaigns/CampaignApi';
import { useRequiredCampaignApi } from '../../../api/campaigns/CampaignApiProvider';
import type { Campaign } from '../../../api/campaigns/types';
import { OwnerApiError } from '../../../api/owner/OwnerApi';
import { CLUB_TIMEZONE } from '../../../owner/form';
import { Button } from '../../../ui/Button';
import { Dialog } from '../../../ui/Dialog';
import dialogStyles from '../../../ui/Dialog.module.css';
import formStyles from '../OwnerEventForm.module.css';

interface Props {
  campaignId: string;
  recipients: number;
  onSent(c: Campaign): void;
  /** Closed: by the owner, or by an error that belongs on the editor's form. */
  onClose(error?: unknown): void;
}

const MONTHS = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];

const one = (n: number) => n % 10 === 1 && n % 100 !== 11;
/** «Отправить 37 гостям?» */
const toGuests = (n: number) => `${n} ${one(n) ? 'гостю' : 'гостям'}`;
/** «для 214 гостей» */
const ofGuests = (n: number) => `${n} ${one(n) ? 'гостя' : 'гостей'}`;

/** Club-local date and time (yyyy-mm-dd, hh:mm) of an instant. */
function clubParts(ms: number): { date: string; time: string } {
  const parts = new Intl.DateTimeFormat('sv-SE', {
    timeZone: CLUB_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(new Date(ms));
  const [date, time] = parts.split(' ');
  return { date, time };
}

/** The club is in Moscow, UTC+3 all year. */
const clubInstant = (date: string, time: string) => `${date}T${time}:00+03:00`;

function whenLabel(date: string, time: string): string {
  const [, month, day] = date.split('-').map(Number);
  return `${day} ${MONTHS[month - 1]}, ${time}`;
}

/** Now or later, then «are you sure», and the night offer when the server asks for it (spec §6). */
export function SendFlow({ campaignId, recipients, onSent, onClose }: Props) {
  const api = useRequiredCampaignApi();
  const [mode, setMode] = useState<'now' | 'later'>('now');
  const [start] = useState(() => clubParts(Date.now() + 60 * 60 * 1000));
  const [date, setDate] = useState(start.date);
  const [time, setTime] = useState(start.time.slice(0, 3) + '00');
  const [step, setStep] = useState<'choose' | 'confirm' | 'night'>('choose');
  const [night, setNight] = useState<QuietHoursError | null>(null);
  const [atError, setAtError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);

  async function send(at: string | null) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    try {
      onSent(await api.send(campaignId, at));
    } catch (error) {
      if (error instanceof QuietHoursError) {
        setNight(error);
        setStep('night');
      } else if (error instanceof OwnerApiError && error.field === 'at') {
        setAtError(error.message);
        setStep('choose');
      } else {
        onClose(error);
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  if (step === 'confirm') {
    return (
      <Dialog
        title={
          mode === 'now'
            ? `Отправить ${toGuests(recipients)}?`
            : `Запланировать на ${whenLabel(date, time)} для ${ofGuests(recipients)}?`
        }
        text={mode === 'now' ? 'Рассылка уйдёт сразу, отменить её будет нельзя.' : 'До отправки её можно отменить.'}
        confirmLabel={mode === 'now' ? 'Отправить' : 'Запланировать'}
        cancelLabel="Не сейчас"
        busy={busy}
        onConfirm={() => void send(mode === 'now' ? null : new Date(clubInstant(date, time)).toISOString())}
        onCancel={() => setStep('choose')}
      />
    );
  }

  if (step === 'night' && night) {
    return (
      <Dialog
        title={night.message}
        text="Ночью сообщения будят людей. Утром рассылка уйдёт сама."
        confirmLabel="Да"
        cancelLabel="Нет"
        busy={busy}
        onConfirm={() => void send(night.suggestedAt)}
        onCancel={() => onClose()}
      />
    );
  }

  return (
    <div className={dialogStyles.overlay} onClick={() => onClose()}>
      <div
        className={dialogStyles.sheet}
        role="dialog"
        aria-modal="true"
        aria-label="Отправка"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === 'Escape' && onClose()}
      >
        <h2 className={dialogStyles.title}>Когда отправить</h2>
        <div className={formStyles.fields}>
          {(['now', 'later'] as const).map((m) => (
            <label key={m} className={formStyles.switchRow}>
              <span>{m === 'now' ? 'Сейчас' : 'Запланировать'}</span>
              <input type="radio" name="send-mode" checked={mode === m} onChange={() => setMode(m)} />
            </label>
          ))}
          {mode === 'later' ? (
            <div className={formStyles.pair}>
              <div className={formStyles.field}>
                <label htmlFor="send-date" className={formStyles.label}>
                  Дата
                </label>
                <input
                  id="send-date"
                  className={formStyles.input}
                  type="date"
                  value={date}
                  onChange={(e) => {
                    setDate(e.target.value);
                    setAtError(null);
                  }}
                />
              </div>
              <div className={formStyles.field}>
                <label htmlFor="send-time" className={formStyles.label}>
                  Время, МСК
                </label>
                <input
                  id="send-time"
                  className={formStyles.input}
                  type="time"
                  value={time}
                  aria-invalid={atError ? true : undefined}
                  aria-describedby={atError ? 'send-at-error' : undefined}
                  onChange={(e) => {
                    setTime(e.target.value);
                    setAtError(null);
                  }}
                />
                {atError ? (
                  <p id="send-at-error" className={formStyles.error}>
                    {atError}
                  </p>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
        <div className={dialogStyles.actions}>
          <Button wide disabled={mode === 'later' && (!date || !time)} onClick={() => setStep('confirm')}>
            Дальше
          </Button>
          <Button wide variant="secondary" onClick={() => onClose()}>
            Отмена
          </Button>
        </div>
      </div>
    </div>
  );
}
