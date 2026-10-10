import { TriangleAlert } from 'lucide-react';
import { Button } from './Button';
import styles from './State.module.css';

interface ErrorStateProps {
  title: string;
  text: string;
  actionLabel: string;
  onAction: () => void;
}

export function ErrorState({ title, text, actionLabel, onAction }: ErrorStateProps) {
  return (
    <section className={styles.state} role="alert">
      <TriangleAlert className={styles.icon} size={40} strokeWidth={1.5} aria-hidden="true" />
      <h2 className={styles.title}>{title}</h2>
      <p className={styles.text}>{text}</p>
      <Button variant="outline" onClick={onAction}>
        {actionLabel}
      </Button>
    </section>
  );
}
