import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { useRequiredCampaignApi } from '../../../api/campaigns/CampaignApiProvider';
import type { CampaignTemplate } from '../../../api/campaigns/types';
import { visibleText } from '../../../owner/campaigns/text';
import { useBackButton } from '../../../telegram/hooks';
import { Skeleton } from '../../../ui/Skeleton';
import { OwnerLoadError } from '../OwnerLoadError';
import styles from './templates.module.css';

export const firstLine = (body: string) => visibleText(body).split('\n')[0] ?? '';

/** «Новая рассылка»: from a blank page or from a template (spec §7). */
export function CampaignStart() {
  const api = useRequiredCampaignApi();
  const navigate = useNavigate();
  const templates = useQuery({ queryKey: ['campaigns', 'templates'], queryFn: () => api.templates() });
  useBackButton(() => navigate('/owner/campaigns'));

  const ready = templates.data?.filter((t) => t.isBuiltin) ?? [];
  const own = templates.data?.filter((t) => !t.isBuiltin) ?? [];

  return (
    <main className={styles.page}>
      <h1 className="t-h1">Новая рассылка</h1>
      <div className={styles.section}>
        <Link to="/owner/campaigns/new" className={`glass ${styles.card}`}>
          <span className="t-h3">С чистого листа</span>
        </Link>
      </div>
      {templates.isError ? (
        <OwnerLoadError error={templates.error} onRetry={() => void templates.refetch()} />
      ) : templates.isPending ? (
        <div className={styles.section}>
          <Skeleton height={64} />
        </div>
      ) : (
        <>
          <section className={styles.section} aria-labelledby="ready-title">
            <h2 id="ready-title" className={`t-h2 ${styles.sectionTitle}`}>
              Готовые шаблоны
            </h2>
            <TemplateLinks items={ready} />
          </section>
          <section className={styles.section} aria-labelledby="own-title">
            <h2 id="own-title" className={`t-h2 ${styles.sectionTitle}`}>
              Свои шаблоны
            </h2>
            {own.length === 0 ? (
              <p className={styles.empty}>
                Своих шаблонов пока нет. Сохрани рассылку как шаблон или создай в «Шаблонах»
              </p>
            ) : (
              <TemplateLinks items={own} />
            )}
          </section>
        </>
      )}
    </main>
  );
}

function TemplateLinks({ items }: { items: CampaignTemplate[] }) {
  return (
    <ul className={styles.list}>
      {items.map((t) => (
        <li key={t.id}>
          <Link to={`/owner/campaigns/new?template=${t.id}`} className={`glass ${styles.card}`}>
            <span className={`t-h3 ${styles.name}`}>{t.name}</span>
            <span className={styles.preview}>{firstLine(t.body)}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
