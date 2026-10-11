import type { LucideIcon } from 'lucide-react';
import { Button } from './Button';
import styles from './State.module.css';

interface EmptyStateProps {
  title: string;
  text: string;
  icon?: LucideIcon;
  action?: { label: string; onClick: () => void };
}

export function EmptyState({ title, text, icon: Icon, action }: EmptyStateProps) {
  return (
    <section className={styles.state}>
      {Icon ? <Icon className={styles.icon} size={40} strokeWidth={1.5} aria-hidden="true" /> : null}
      <h2 className={styles.title}>{title}</h2>
      <p className={styles.text}>{text}</p>
      {action ? (
        <Button variant="secondary" onClick={action.onClick}>
          {action.label}
        </Button>
      ) : null}
    </section>
  );
}
