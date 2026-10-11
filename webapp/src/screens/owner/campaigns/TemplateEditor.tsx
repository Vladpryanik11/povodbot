import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useRequiredCampaignApi } from '../../../api/campaigns/CampaignApiProvider';
import { CMSG } from '../../../api/campaigns/messages';
import type { CampaignButton, CampaignTemplate, ImageKind } from '../../../api/campaigns/types';
import { OwnerApiError } from '../../../api/owner/OwnerApi';
import { MSG } from '../../../api/owner/messages';
import { bodyError, buttonsError, trimButtons } from '../../../owner/campaigns/rules';
import { htmlToMarkup, markupToHtml, textLimit } from '../../../owner/campaigns/text';
import { useBackButton, useMainButton } from '../../../telegram/hooks';
import { Button } from '../../../ui/Button';
import { Skeleton } from '../../../ui/Skeleton';
import { Field } from '../Field';
import { OwnerLoadError } from '../OwnerLoadError';
import { ButtonsEditor } from './parts/ButtonsEditor';
import { TextEditor } from './parts/TextEditor';
import styles from './templates.module.css';

const NAME_LIMIT = 100;
const IMAGES: { kind: ImageKind; title: string }[] = [
  { kind: 'event', title: 'Афиша вечера' },
  { kind: 'upload', title: 'Своя' },
  { kind: 'none', title: 'Без картинки' },
];

type Errors = Partial<Record<'name' | 'body' | 'buttons', string>>;

/** Create (`/templates/new`) or edit an own template; a ready one opens read-only. */
export function TemplateEditor() {
  const { id = 'new' } = useParams();
  const api = useRequiredCampaignApi();
  const templates = useQuery({ queryKey: ['campaigns', 'templates'], queryFn: () => api.templates() });
  const existing = id === 'new' ? null : (templates.data?.find((t) => t.id === id) ?? null);

  if (id !== 'new') {
    if (templates.isError) return <Shell><OwnerLoadError error={templates.error} onRetry={() => void templates.refetch()} /></Shell>;
    if (templates.isPending) return <Shell><Skeleton height={200} /></Shell>;
    if (!existing) return <Shell><OwnerLoadError error={new OwnerApiError(404, CMSG.templateNotFound)} onRetry={() => void templates.refetch()} /></Shell>;
  }
  return <Form key={existing?.id ?? 'new'} template={existing} />;
}

function Shell({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  useBackButton(() => navigate('/owner/campaigns/templates'));
  return (
    <main className={styles.page}>
      <h1 className="t-h1">Шаблон</h1>
      {children}
    </main>
  );
}

function Form({ template }: { template: CampaignTemplate | null }) {
  const api = useRequiredCampaignApi();
  const navigate = useNavigate();
  const client = useQueryClient();
  const locked = template?.isBuiltin ?? false;
  const [name, setName] = useState(template?.name ?? '');
  const [body, setBody] = useState(htmlToMarkup(template?.body ?? ''));
  const [imageKind, setImageKind] = useState<ImageKind>(template?.imageKind ?? 'event');
  const [buttons, setButtons] = useState<CampaignButton[]>(template?.buttons ?? []);
  const [errors, setErrors] = useState<Errors>({});
  const [banner, setBanner] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setErrors({});
  }, [name, body, imageKind, buttons]);

  const back = () => navigate('/owner/campaigns/templates');
  useBackButton(back);

  const refresh = () => client.invalidateQueries({ queryKey: ['campaigns', 'templates'] });

  async function copyToOwn() {
    if (!template || busy) return;
    setBusy(true);
    try {
      await api.createTemplate({
        name: `${template.name}${CMSG.copySuffix}`,
        body: template.body,
        imageKind: template.imageKind,
        buttons: template.buttons,
      });
      await refresh();
      back();
    } catch (error) {
      setBanner(error instanceof OwnerApiError ? error.message : MSG.unknown);
      setBusy(false);
    }
  }

  async function save() {
    if (busy) return;
    const html = markupToHtml(body);
    const trimmed = trimButtons(buttons);
    const found: Errors = {};
    if (!name.trim()) found.name = CMSG.emptyName;
    const bad = bodyError(html, imageKind, { allowEmpty: true });
    if (bad) found.body = bad.message;
    const badButtons = buttonsError(trimmed, true);
    if (badButtons) found.buttons = badButtons.message;
    if (Object.keys(found).length > 0) {
      setErrors(found);
      return;
    }
    setBusy(true);
    setBanner(null);
    try {
      const input = { name: name.trim(), body: html, imageKind, buttons: trimmed };
      if (template) await api.updateTemplate(template.id, input);
      else await api.createTemplate(input);
      await refresh();
      back();
    } catch (error) {
      if (error instanceof OwnerApiError && (error.field === 'name' || error.field === 'body' || error.field === 'buttons')) {
        setErrors({ [error.field]: error.message });
      } else {
        setBanner(error instanceof OwnerApiError ? error.message : MSG.unknown);
      }
      setBusy(false);
    }
  }

  useMainButton(
    locked ? null : { text: 'Сохранить', enabled: !busy, progress: busy, onClick: () => void save() },
  );

  return (
    <main className={styles.page}>
      <h1 className="t-h1">{template ? template.name : 'Новый шаблон'}</h1>
      {locked ? <p className={styles.hint}>{CMSG.builtinLocked}</p> : null}
      {banner ? (
        <p role="alert" className={styles.banner}>
          {banner}
        </p>
      ) : null}
      <fieldset className={styles.fields} disabled={locked || busy}>
        <Field id="template-name" label="Название" error={errors.name}>
          {(p) => <input {...p} type="text" maxLength={NAME_LIMIT} value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <TextEditor id="template-body" value={body} onChange={setBody} limit={textLimit(imageKind)} error={errors.body} />
        <p className={styles.hint}>{'{event} и {date} заменятся, когда выберешь вечер'}</p>
        <Field id="template-image" label="Картинка">
          {(p) => (
            <select {...p} value={imageKind} onChange={(e) => setImageKind(e.target.value as ImageKind)}>
              {IMAGES.map((i) => (
                <option key={i.kind} value={i.kind}>
                  {i.title}
                </option>
              ))}
            </select>
          )}
        </Field>
        <ButtonsEditor buttons={buttons} onChange={setButtons} hasEvent error={errors.buttons} />
      </fieldset>
      {locked ? (
        <div className={styles.section}>
          <Button wide loading={busy} onClick={() => void copyToOwn()}>
            Скопировать в свои
          </Button>
        </div>
      ) : null}
    </main>
  );
}
