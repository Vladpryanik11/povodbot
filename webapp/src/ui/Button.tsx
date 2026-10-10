import type { ButtonHTMLAttributes, ReactNode } from 'react';
import styles from './Button.module.css';

interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  variant?: 'primary' | 'outline' | 'link';
  loading?: boolean;
  wide?: boolean;
  children: ReactNode;
}

export function Button({ variant = 'primary', loading = false, wide = false, className, children, ...rest }: ButtonProps) {
  const classes = [styles.button, styles[variant], wide ? styles.wide : '', className ?? ''].join(' ');
  return (
    <button type="button" {...rest} className={classes} aria-busy={loading || undefined}>
      {/* The label stays in the layout while loading, so the button keeps its width. */}
      <span className={`${styles.label} ${loading ? styles.hidden : ''}`}>{children}</span>
      {loading ? <span className={styles.spinner} aria-hidden="true" /> : null}
    </button>
  );
}
