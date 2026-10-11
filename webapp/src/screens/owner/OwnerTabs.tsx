import { Link } from 'react-router-dom';
import { useCampaignAccess } from '../../owner/campaigns/useCampaignAccess';
import { useOwnerAccess } from '../../owner/useOwnerAccess';
import styles from './OwnerTabs.module.css';

const TABS = [
  { id: 'events', title: 'Вечера', to: '/owner' },
  { id: 'campaigns', title: 'Рассылки', to: '/owner/campaigns' },
] as const;

/** «Вечера | Рассылки» in owner mode; only for a role that has both. */
export function OwnerTabs({ current }: { current: 'events' | 'campaigns' }) {
  const events = useOwnerAccess();
  const campaigns = useCampaignAccess();
  if (!events || !campaigns) return null;
  return (
    <nav className={`glass ${styles.tabs}`} aria-label="Режим владельца">
      {TABS.map((tab) => (
        <Link
          key={tab.id}
          to={tab.to}
          className={`${styles.tab} ${tab.id === current ? styles.on : ''}`}
          aria-current={tab.id === current ? 'page' : undefined}
        >
          {tab.title}
        </Link>
      ))}
    </nav>
  );
}
