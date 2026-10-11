import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { useRequiredCampaignApi } from '../../../api/campaigns/CampaignApiProvider';
import { CMSG } from '../../../api/campaigns/messages';
import type { CampaignTemplate } from '../../../api/campaigns/types';
import { OwnerApiError } from '../../../api/owner/OwnerApi';
import { MSG } from '../../../api/owner/messages';
import { useBackButton, useMainButton } from '../../../telegram/hooks';
import { Button } from '../../../ui/Button';
import { Dialog } from '../../../ui/Dialog';
import { Skeleton } from '../../../ui/Skeleton';
import { OwnerLoadError } from '../OwnerLoadError';
import { firstLine } from './CampaignStart';
import styles from './templates.module.css';

/** «Шаблоны»: ready ones (use, copy) and own ones (use, edit, delete). */
export function Templates() {
  const api = useRequiredCampaignApi();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [deleting, setDeleting] = useState<CampaignTemplate | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const templates = useQuery({ queryKey: ['campaigns', 'templates'], queryFn: () => api.templates() });
  const done = () => {
    setProblem(null);
    return client.invalidateQueries({ queryKey: ['campaigns', 'templates'] });
  };
  const fail = (e: unknown) => setProblem(e instanceof OwnerApiError ? e.message : MSG.unknown);

  const copy = useMutation({
    mutationFn: (t: CampaignTemplate) =>
      api.createTemplate({
        name: `${t.name}${CMSG.copySuffix}`,
        body: t.body,
        imageKind: t.imageKind,
        buttons: t.buttons,
      }),
    onSuccess: done,
    onError: fail,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteTemplate(id),
    onSuccess: done,
    onError: fail,
  });

  useMainButton(
    templates.isError
      ? null
      : {
          text: '+ Новый шаблон',
          enabled: true,
          progress: false,
          onClick: () => navigate('/owner/campaigns/templates/new'),
        },
  );
  useBackButton(() => navigate('/owner/campaigns'));

  const ready = templates.data?.filter((t) => t.isBuiltin) ?? [];
  const own = templates.data?.filter((t) => !t.isBuiltin) ?? [];
  const use = (id: string) => (
    <Button onClick={() => navigate(`/owner/campaigns/new?template=${id}`)}>Использовать</Button>
  );

  return (
    <main className={styles.page}>
      <h1 className="t-h1">Шаблоны</h1>
      {problem ? (
        <p role="alert" className={styles.banner}>
          {problem}
        </p>
      ) : null}
      {templates.isError ? (
        <OwnerLoadError error={templates.error} onRetry={() => void templates.refetch()} />
      ) : templates.isPending ? (
        <div className={styles.section}>
          <Skeleton height={86} />
        </div>
      ) : (
        <>
          <section className={styles.section} aria-labelledby="ready-title">
            <h2 id="ready-title" className={`t-h2 ${styles.sectionTitle}`}>
              Готовые
            </h2>
            <ul className={styles.list}>
              {ready.map((t) => (
                <Card key={t.id} t={t}>
                  {use(t.id)}
                  <Button variant="secondary" loading={copy.isPending && copy.variables?.id === t.id} onClick={() => copy.mutate(t)}>
                    Скопировать в свои
                  </Button>
                </Card>
              ))}
            </ul>
          </section>
          <section className={styles.section} aria-labelledby="own-title">
            <h2 id="own-title" className={`t-h2 ${styles.sectionTitle}`}>
              Свои
            </h2>
            {own.length === 0 ? (
              <p className={styles.empty}>Своих шаблонов пока нет</p>
            ) : (
              <ul className={styles.list}>
                {own.map((t) => (
                  <Card key={t.id} t={t}>
                    {use(t.id)}
                    <Button variant="secondary" onClick={() => navigate(`/owner/campaigns/templates/${t.id}`)}>
                      Править
                    </Button>
                    <Button variant="secondary" onClick={() => setDeleting(t)}>
                      Удалить
                    </Button>
                  </Card>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
      {deleting ? (
        <Dialog
          title="Удалить шаблон?"
          text={`«${deleting.name}» пропадёт из своих шаблонов.`}
          confirmLabel="Удалить"
          cancelLabel="Оставить"
          onConfirm={() => {
            remove.mutate(deleting.id);
            setDeleting(null);
          }}
          onCancel={() => setDeleting(null)}
        />
      ) : null}
    </main>
  );
}

function Card({ t, children }: { t: CampaignTemplate; children: ReactNode }) {
  return (
    <li className={`glass ${styles.card}`}>
      <span className={`t-h3 ${styles.name}`}>{t.name}</span>
      <span className={styles.preview}>{firstLine(t.body)}</span>
      <div className={styles.actions}>{children}</div>
    </li>
  );
}
