import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useId, useMemo, useRef, useState, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { MSG } from '../../api/owner/messages';
import { OwnerApiError } from '../../api/owner/OwnerApi';
import { useOwnerApi, useOwnerDrafts } from '../../api/owner/OwnerApiProvider';
import type { OwnerEvent } from '../../api/owner/types';
import {
  emptyForm,
  FORM_FIELDS,
  formFromEvent,
  formToInput,
  publishGaps,
  type EventForm,
  type FormField,
} from '../../owner/form';
import { ownerStatus } from '../../owner/status';
import { useBackButton, useClosingConfirmation, useMainButton } from '../../telegram/hooks';
import { Button } from '../../ui/Button';
import { Pill } from '../../ui/Pill';
import { Skeleton } from '../../ui/Skeleton';
import { Toggle } from '../../ui/Toggle';
import { OwnerLoadError } from './OwnerLoadError';
import { TicketRowsEditor } from './TicketRowsEditor';
import styles from './OwnerEventForm.module.css';

type Errors = Partial<Record<FormField, string>>;

interface Banner {
  text: string;
  /** The evening changed elsewhere: offer to load the fresh version. */
  reload?: boolean;
}

/** What «Свой цвет афиши» starts from. */
const DEFAULT_ACCENT = '#E8A33D';

const READ_ONLY: Partial<Record<OwnerEvent['status'], string>> = {
  completed: 'Вечер прошёл — править нельзя',
  cancelled: 'Вечер отменён — править нельзя',
};

const isFormField = (field: string | null): field is FormField =>
  field !== null && (FORM_FIELDS as readonly string[]).includes(field);

/** Route entry: one screen per evening, so a saved «new» starts clean at its own address. */
export function OwnerEventForm() {
  const { id = 'new' } = useParams();
  return <EventFormScreen key={id} id={id} />;
}

/** The evening's form: edit, save as a draft (spec §3.2). `id === 'new'` is an evening not created yet. */
function EventFormScreen({ id }: { id: string }) {
  const isNew = id === 'new';
  const api = useOwnerApi();
  const drafts = useOwnerDrafts();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const ids = useId();
  const eventQuery = useQuery({ queryKey: ['owner', 'event', id], queryFn: () => api.event(id), enabled: !isNew });
  const directions = useQuery({ queryKey: ['owner', 'directions'], queryFn: () => api.directions() });
  const event = eventQuery.data;

  const [blank] = useState(emptyForm);
  const [edited, setEdited] = useState<EventForm | undefined>(() => drafts.get(id));
  const [dirty, setDirty] = useState(() => drafts.get(id) !== undefined);
  const [errors, setErrors] = useState<Errors>({});
  const [banner, setBanner] = useState<Banner | null>(null);
  const [saving, setSaving] = useState(false);
  const inFlight = useRef(false);
  const [acting, setActing] = useState(false);
  const actInFlight = useRef(false);

  const savedForm = useMemo(() => (event ? formFromEvent(event) : undefined), [event]);
  /** Unsaved input first, else the saved evening. */
  const form: EventForm | undefined = edited ?? (isNew ? blank : savedForm);
  const ready = form !== undefined && directions.data !== undefined && (isNew || event !== undefined);
  const readOnlyText = event ? READ_ONLY[event.status] : undefined;

  function change(patch: Partial<EventForm>, field: FormField) {
    if (!form) return;
    const next = { ...form, ...patch };
    setEdited(next);
    drafts.set(id, next);
    setDirty(true);
    setErrors((prev) => {
      const rest = { ...prev };
      delete rest[field];
      return rest;
    });
  }

  function showError(error: unknown) {
    if (!(error instanceof OwnerApiError)) {
      setBanner({ text: MSG.unknown });
    } else if (error.status === 0) {
      setBanner({ text: MSG.network });
    } else if (error.status === 409) {
      setBanner({ text: error.message, reload: true });
    } else if (isFormField(error.field)) {
      setErrors({ [error.field]: error.message });
    } else {
      setBanner({ text: error.message });
    }
  }

  async function save(): Promise<OwnerEvent | null> {
    if (inFlight.current || !form) return null;
    const checked = formToInput(form);
    if (!checked.ok) {
      setErrors({ [checked.field]: checked.message });
      return null;
    }
    inFlight.current = true;
    setSaving(true);
    setErrors({});
    setBanner(null);
    try {
      const result = isNew
        ? await api.createEvent(checked.input)
        : await api.updateEvent(id, { ...checked.input, updatedAt: event!.updatedAt });
      queryClient.setQueryData(['owner', 'event', result.id], result);
      void queryClient.invalidateQueries({ queryKey: ['owner', 'events'] });
      drafts.clear(id);
      if (isNew) {
        navigate(`/owner/events/${result.id}`, { replace: true });
      } else {
        // Back to the saved evening: new tickets now carry their ids, so the next save does not add them again.
        setEdited(undefined);
        setDirty(false);
      }
      return result;
    } catch (error) {
      showError(error);
      return null;
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  }

  /** Publish or unpublish: one at a time, the answer becomes the evening on screen. */
  async function act(run: () => Promise<OwnerEvent | null>, onError: (error: unknown) => void = showError) {
    if (actInFlight.current) return;
    actInFlight.current = true;
    setActing(true);
    setBanner(null);
    try {
      const result = await run();
      if (result) {
        queryClient.setQueryData(['owner', 'event', id], result);
        void queryClient.invalidateQueries({ queryKey: ['owner', 'events'] });
      }
    } catch (error) {
      onError(error);
    } finally {
      actInFlight.current = false;
      setActing(false);
    }
  }

  const publish = () =>
    act(async () => {
      // Unsaved input goes first; if it does not save, its error is already on screen.
      if (dirty && !(await save())) return null;
      return api.publish(id);
    });

  const unpublish = () =>
    act(
      () => api.unpublish(id),
      (error) => {
        // 409 here is «there are orders», not a stale version: nothing to reload.
        if (error instanceof OwnerApiError && error.status === 409) setBanner({ text: error.message });
        else showError(error);
      },
    );

  async function reload() {
    drafts.clear(id);
    setEdited(undefined);
    setDirty(false);
    setErrors({});
    setBanner(null);
    const fresh = await eventQuery.refetch();
    if (fresh.error) showError(fresh.error);
  }

  useMainButton(
    ready && !readOnlyText ? { text: 'Сохранить', enabled: dirty && !saving, progress: saving, onClick: () => void save() } : null,
  );
  useBackButton(() => navigate('/owner'));
  useClosingConfirmation(dirty);

  if (!ready) {
    const error = (isNew ? null : eventQuery.error) ?? directions.error;
    return (
      <main className={styles.page}>
        {error ? (
          <OwnerLoadError
            error={error}
            onRetry={() => {
              if (!isNew) void eventQuery.refetch();
              void directions.refetch();
            }}
          />
        ) : (
          <div className={styles.fields}>
            <Skeleton height={32} />
            <Skeleton height={76} />
            <Skeleton height={76} />
            <Skeleton height={160} />
          </div>
        )}
      </main>
    );
  }

  const fid = (name: string) => `${ids}-${name}`;
  const status = event ? ownerStatus(event, false) : null;
  const gaps = publishGaps(form, Boolean(event?.poster));

  return (
    <main className={styles.page}>
      <h1 className={`t-h1 ${styles.title}`}>{isNew ? 'Новый вечер' : event!.title}</h1>
      {status ? (
        <div className={styles.status}>
          <Pill tone={status.tone}>{status.text}</Pill>
        </div>
      ) : null}
      {readOnlyText ? <p className={`glass ${styles.banner}`}>{readOnlyText}</p> : null}
      {banner ? (
        <div role="alert" className={`glass ${styles.banner}`}>
          <p>{banner.text}</p>
          {banner.reload ? (
            <Button variant="secondary" onClick={() => void reload()}>
              Загрузить свежую версию
            </Button>
          ) : null}
        </div>
      ) : null}
      <fieldset className={styles.fields} disabled={Boolean(readOnlyText)}>
        <Field id={fid('title')} label="Название" error={errors.title}>
          {(p) => <input {...p} value={form.title} onChange={(e) => change({ title: e.target.value }, 'title')} />}
        </Field>
        <Field id={fid('direction')} label="Направление" error={errors.directionId}>
          {(p) => (
            <select {...p} value={form.directionId} onChange={(e) => change({ directionId: e.target.value }, 'directionId')}>
              <option value="">Выбери направление</option>
              {directions.data!.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          )}
        </Field>
        <div className={styles.pair}>
          <Field id={fid('starts')} label="Начало" error={errors.startsAt}>
            {(p) => (
              <input
                {...p}
                type="datetime-local"
                value={form.startsLocal}
                onChange={(e) => change({ startsLocal: e.target.value }, 'startsAt')}
              />
            )}
          </Field>
          <Field id={fid('ends')} label="Конец" error={errors.endsAt}>
            {(p) => (
              <input
                {...p}
                type="datetime-local"
                value={form.endsLocal}
                onChange={(e) => change({ endsLocal: e.target.value }, 'endsAt')}
              />
            )}
          </Field>
        </div>
        <div className={styles.switchRow}>
          <span aria-hidden="true">Место уточняется</span>
          <Toggle label="Место уточняется" checked={form.venueTbd} onChange={(venueTbd) => change({ venueTbd }, 'address')} />
        </div>
        {form.venueTbd ? null : (
          <Field id={fid('address')} label="Адрес" error={errors.address}>
            {(p) => <input {...p} value={form.address} onChange={(e) => change({ address: e.target.value }, 'address')} />}
          </Field>
        )}
        <Field id={fid('map')} label="Ссылка на карту" error={errors.mapUrl}>
          {(p) => (
            <input
              {...p}
              type="url"
              inputMode="url"
              value={form.mapUrl}
              onChange={(e) => change({ mapUrl: e.target.value }, 'mapUrl')}
            />
          )}
        </Field>
        <Field id={fid('description')} label="Описание" error={errors.description}>
          {(p) => (
            <textarea
              {...p}
              rows={5}
              value={form.description}
              onChange={(e) => change({ description: e.target.value }, 'description')}
            />
          )}
        </Field>
        <Field id={fid('capacity')} label="Вместимость" error={errors.capacity}>
          {(p) => (
            <input
              {...p}
              inputMode="numeric"
              autoComplete="off"
              value={form.capacity}
              onChange={(e) => change({ capacity: e.target.value }, 'capacity')}
            />
          )}
        </Field>
        <div className={styles.switchRow}>
          <span aria-hidden="true">Свой цвет афиши</span>
          <Toggle
            label="Свой цвет афиши"
            checked={form.accentColor !== ''}
            onChange={(on) => change({ accentColor: on ? DEFAULT_ACCENT : '' }, 'accentColor')}
          />
        </div>
        {form.accentColor !== '' ? (
          <Field id={fid('accent')} label="Цвет афиши" error={errors.accentColor}>
            {(p) => (
              <input
                {...p}
                type="color"
                className={`${p.className} ${styles.color}`}
                value={form.accentColor || DEFAULT_ACCENT}
                onChange={(e) => change({ accentColor: e.target.value }, 'accentColor')}
              />
            )}
          </Field>
        ) : null}
        <TicketRowsEditor
          rows={form.tickets}
          error={errors.ticketTypes}
          onChange={(tickets) => change({ tickets }, 'ticketTypes')}
        />
      </fieldset>
      {readOnlyText ? null : event?.status === 'published' ? (
        <div className={styles.publish}>
          <Button variant="secondary" wide loading={acting} onClick={() => void unpublish()}>
            Снять с публикации
          </Button>
        </div>
      ) : (
        <div className={styles.publish}>
          <Button wide disabled={gaps.length > 0} loading={acting} onClick={() => void publish()}>
            Опубликовать
          </Button>
          {gaps.length > 0 ? <p className={styles.hint}>{`Чтобы опубликовать, добавь: ${gaps.join(', ')}`}</p> : null}
        </div>
      )}
    </main>
  );
}

interface ControlProps {
  id: string;
  className: string;
  'aria-describedby'?: string;
  'aria-invalid'?: true;
}

/** A visible label over its control, and the error under it, tied by aria-describedby. */
function Field({
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
