import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useId, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useRequiredCampaignApi } from '../../../api/campaigns/CampaignApiProvider';
import type { Campaign, CampaignTemplate, ImageKind } from '../../../api/campaigns/types';
import { MSG } from '../../../api/owner/messages';
import { OwnerApiError } from '../../../api/owner/OwnerApi';
import { useOwnerApi } from '../../../api/owner/OwnerApiProvider';
import {
  formErrors,
  formFromCampaign,
  formFromTemplate,
  formToInput,
  pickEvent,
  sendBlocker,
  type CampaignForm,
  type CampaignFormErrors,
  type CampaignFormField,
} from '../../../owner/campaigns/form';
import { campaignStatus } from '../../../owner/campaigns/labels';
import { textLimit } from '../../../owner/campaigns/text';
import { useAudienceCount } from '../../../owner/campaigns/useAudienceCount';
import { useBackButton, useClosingConfirmation, useMainButton } from '../../../telegram/hooks';
import { Button } from '../../../ui/Button';
import { Dialog } from '../../../ui/Dialog';
import { Pill } from '../../../ui/Pill';
import { Field } from '../Field';
import { AudienceEditor } from './parts/AudienceEditor';
import { ButtonsEditor } from './parts/ButtonsEditor';
import { MessageBubble } from './parts/MessageBubble';
import { TextEditor } from './parts/TextEditor';
import { SendFlow } from './SendFlow';
import styles from '../OwnerEventForm.module.css';

interface Banner {
  text: string;
  reload?: boolean;
  /** Good news, not a problem. */
  ok?: boolean;
}

const FIELDS: readonly string[] = ['title', 'eventId', 'body', 'image', 'buttons', 'audience'];
const isField = (field: string | null): field is CampaignFormField => field !== null && FIELDS.includes(field);

const IMAGE_LABEL: Record<ImageKind, string> = { event: 'Афиша вечера', upload: 'Своя', none: 'Без картинки' };

interface Props {
  /** null: not created yet. */
  campaign: Campaign | null;
  /** A new campaign starts from it; null is a blank sheet. */
  template?: CampaignTemplate | null;
}

/** A draft or scheduled campaign: what, to whom, how it looks (spec §5). */
export function CampaignEditor({ campaign, template = null }: Props) {
  const api = useRequiredCampaignApi();
  const ownerApi = useOwnerApi();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const ids = useId();
  const upcoming = useQuery({ queryKey: ['owner', 'events', 'all'], queryFn: () => ownerApi.events('all') });
  const past = useQuery({ queryKey: ['owner', 'events', 'past'], queryFn: () => ownerApi.events('past') });
  const directions = useQuery({ queryKey: ['owner', 'directions'], queryFn: () => ownerApi.directions() });

  const [base] = useState(() => (campaign ? formFromCampaign(campaign) : formFromTemplate(template)));
  const [edited, setEdited] = useState<CampaignForm | undefined>(undefined);
  const [errors, setErrors] = useState<CampaignFormErrors>({});
  const [banner, setBanner] = useState<Banner | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  // A new campaign is saved first and opens again under its id, still on its way to the send sheet.
  const location = useLocation();
  const [sending, setSending] = useState(() => (location.state as { send?: boolean } | null)?.send === true);

  const form = edited ?? (campaign ? formFromCampaign(campaign) : base);
  const dirty = edited !== undefined || campaign === null;
  const audience = useAudienceCount(form.audience);
  const scheduled = campaign?.status === 'scheduled';

  const allUpcoming = upcoming.data ?? [];
  const eventOptions = allUpcoming.filter((e) => e.status === 'published' || e.id === form.eventId);
  const audienceEvents = [...allUpcoming.filter((e) => e.status === 'published'), ...(past.data ?? [])];
  const selected = allUpcoming.find((e) => e.id === form.eventId) ?? past.data?.find((e) => e.id === form.eventId);

  const local = formErrors(form);
  const shownErrors: CampaignFormErrors = { ...local, ...errors };
  const blocker = sendBlocker(form);

  function change(next: CampaignForm, ...fields: CampaignFormField[]) {
    setEdited(next);
    setErrors((prev) => {
      const rest = { ...prev };
      for (const f of fields) delete rest[f];
      return rest;
    });
  }

  function showError(error: unknown) {
    if (!(error instanceof OwnerApiError)) setBanner({ text: MSG.unknown });
    else if (error.status === 0) setBanner({ text: MSG.network });
    else if (error.status === 409) setBanner({ text: error.message, reload: true });
    else if (isField(error.field)) setErrors({ [error.field]: error.message });
    else setBanner({ text: error.message });
  }

  function settle(result: Campaign) {
    queryClient.setQueryData(['campaigns', result.id], result);
    void queryClient.invalidateQueries({ queryKey: ['campaigns', 'list'] });
  }

  /** Saves unsaved input; the answer is the campaign as the server has it, or null when it did not save. */
  async function save(state?: { send: true }): Promise<Campaign | null> {
    if (campaign && !dirty) return campaign;
    if (Object.keys(local).length) {
      setErrors(local);
      return null;
    }
    const input = formToInput(form, campaign);
    const result = campaign
      ? await api.updateCampaign(campaign.id, { ...input, updatedAt: campaign.updatedAt })
      : await api.createCampaign(input);
    settle(result);
    if (campaign) setEdited(undefined);
    else navigate(`/owner/campaigns/${result.id}`, { replace: true, state });
    return result;
  }

  /** One action at a time; each saves first. */
  async function run(action: (saved: Campaign) => Promise<string | void>, state?: { send: true }) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setBanner(null);
    setErrors({});
    try {
      const saved = await save(state);
      if (!saved) return;
      const done = await action(saved);
      if (done) setBanner({ text: done, ok: true });
    } catch (error) {
      showError(error);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  async function reload() {
    setEdited(undefined);
    setErrors({});
    setBanner(null);
    if (!campaign) return;
    try {
      settle(await api.campaign(campaign.id));
    } catch (error) {
      showError(error);
    }
  }

  const upload = (file: File) =>
    run(async (saved) => {
      settle(await api.uploadImage(saved.id, file));
      setEdited(undefined);
    });

  const cancel = () => {
    setConfirmCancel(false);
    return run(async (saved) => {
      settle(await api.cancel(saved.id));
    });
  };

  const canSend = !busy && !blocker && Object.keys(shownErrors).length === 0 && (audience.count ?? 0) > 0 && !audience.pending;
  useMainButton(
    scheduled || sending || confirmCancel
      ? null
      : {
          text: 'Отправить…',
          enabled: canSend,
          progress: busy,
          summary: audience.count === 0 ? 'Получат 0' : undefined,
          onClick: () =>
            void run(
              async () => {
                if (campaign) setSending(true);
              },
              campaign ? undefined : { send: true },
            ),
        },
  );
  useBackButton(() => (sending ? setSending(false) : navigate('/owner/campaigns')));
  useClosingConfirmation(edited !== undefined);

  const fid = (name: string) => `${ids}-${name}`;
  const status = campaign ? campaignStatus(campaign) : null;
  const imageUrl =
    form.imageKind === 'event'
      ? (selected?.poster?.url ?? null)
      : form.imageKind === 'upload' && campaign?.image.kind === 'upload'
        ? (campaign.image.url ?? null)
        : null;

  return (
    <main className={styles.page}>
      <h1 className={`t-h1 ${styles.title}`}>{campaign ? campaign.title : 'Новая рассылка'}</h1>
      {status ? (
        <div className={styles.status}>
          <Pill tone={status.tone}>{status.text}</Pill>
        </div>
      ) : null}
      {banner ? (
        <div role={banner.ok ? 'status' : 'alert'} className={`glass ${styles.banner}`}>
          <p>{banner.text}</p>
          {banner.reload ? (
            <Button variant="secondary" onClick={() => void reload()}>
              Загрузить свежую версию
            </Button>
          ) : null}
        </div>
      ) : null}
      <div className={styles.fields}>
        <Field id={fid('title')} label="Название" error={shownErrors.title}>
          {(p) => <input {...p} value={form.title} onChange={(e) => change({ ...form, title: e.target.value }, 'title')} />}
        </Field>
        <Field id={fid('event')} label="Вечер" error={shownErrors.eventId}>
          {(p) => (
            <select
              {...p}
              value={form.eventId ?? ''}
              onChange={(e) =>
                change(pickEvent(form, eventOptions.find((x) => x.id === e.target.value) ?? null), 'eventId', 'image', 'buttons', 'body')
              }
            >
              <option value="">Без вечера</option>
              {eventOptions.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.title}
                </option>
              ))}
            </select>
          )}
        </Field>
        <TextEditor
          id={fid('body')}
          value={form.markup}
          onChange={(markup) => change({ ...form, markup }, 'body')}
          limit={textLimit(form.imageKind)}
          error={shownErrors.body}
        />
        {blocker && blocker !== shownErrors.body ? <p className={styles.hint}>{blocker}</p> : null}
        <fieldset className={styles.tickets}>
          <legend className={styles.label}>Картинка</legend>
          {(['event', 'upload', 'none'] as const).map((kind) => (
            <label key={kind} className={styles.switchRow}>
              <span>{IMAGE_LABEL[kind]}</span>
              <input
                type="radio"
                name={fid('image')}
                checked={form.imageKind === kind}
                disabled={kind === 'event' && form.eventId === null}
                onChange={() => change({ ...form, imageKind: kind, wantsPoster: false }, 'image', 'body')}
              />
            </label>
          ))}
          {form.imageKind === 'upload' ? (
            <Field id={fid('file')} label="Файл картинки">
              {(p) => (
                <input
                  {...p}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  disabled={busy}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) void upload(file);
                  }}
                />
              )}
            </Field>
          ) : null}
          {shownErrors.image ? <p className={styles.error}>{shownErrors.image}</p> : null}
        </fieldset>
        <ButtonsEditor
          buttons={form.buttons}
          onChange={(buttons) => change({ ...form, buttons }, 'buttons')}
          hasEvent={form.eventId !== null}
          error={shownErrors.buttons}
        />
        <AudienceEditor
          value={form.audience}
          onChange={(next) => change({ ...form, audience: next }, 'audience')}
          events={audienceEvents}
          directions={directions.data ?? []}
          audience={audience}
          error={shownErrors.audience}
        />
        <MessageBubble markup={form.markup} imageUrl={imageUrl} buttons={form.buttons} />
      </div>
      <div className={styles.publish}>
        <Button variant="secondary" wide disabled={busy || !dirty} onClick={() => void run(async () => {})}>
          Сохранить черновик
        </Button>
        <Button
          variant="secondary"
          wide
          disabled={busy}
          onClick={() =>
            void run(async (saved) => {
              await api.sendTest(saved.id);
              return 'Отправили тебе в Telegram';
            })
          }
        >
          Отправить себе
        </Button>
        <Button
          variant="secondary"
          wide
          disabled={busy}
          onClick={() =>
            void run(async (saved) => {
              await api.saveAsTemplate(saved.id, saved.title);
              void queryClient.invalidateQueries({ queryKey: ['campaigns', 'templates'] });
              return 'Шаблон сохранён';
            })
          }
        >
          Сохранить как шаблон
        </Button>
        {scheduled ? (
          <Button variant="link" disabled={busy} onClick={() => setConfirmCancel(true)}>
            Отменить рассылку
          </Button>
        ) : null}
      </div>
      {confirmCancel ? (
        <Dialog
          title="Отменить рассылку?"
          text="Её никто не получит. Черновик останется в списке отменённых."
          confirmLabel="Отменить рассылку"
          cancelLabel="Не отменять"
          onConfirm={() => void cancel()}
          onCancel={() => setConfirmCancel(false)}
        />
      ) : null}
      {sending && campaign ? (
        <SendFlow
          campaignId={campaign.id}
          recipients={audience.count ?? 0}
          onSent={(sent) => {
            settle(sent);
            setSending(false);
            navigate(sent.status === 'scheduled' ? '/owner/campaigns?filter=scheduled' : `/owner/campaigns/${sent.id}`);
          }}
          onClose={(error) => {
            setSending(false);
            if (error) showError(error);
          }}
        />
      ) : null}
    </main>
  );
}
