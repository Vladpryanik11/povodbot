import styles from './StatusPill.module.css';

type Props = { kind: 'today' | 'left' | 'soldout'; count?: number };

/** Dark pill on a poster; the dot carries the poster colour, the words stay white (spec v2 §5). */
export function StatusPill({ kind, count }: Props) {
  const text = kind === 'today' ? 'Сегодня' : kind === 'left' ? `Осталось ${count ?? 0}` : 'Мест нет';
  return (
    <span className={styles.pill}>
      {kind === 'soldout' ? null : <span className={styles.dot} data-dot="" aria-hidden="true" />}
      {text}
    </span>
  );
}
