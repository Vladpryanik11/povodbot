import styles from './State.module.css';

export function Skeleton({ height, className }: { height: number | string; className?: string }) {
  return <div className={`${styles.skeleton} ${className ?? ''}`} style={{ height }} aria-hidden="true" />;
}
