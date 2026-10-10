import { ChevronRight, type LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { ICON_STROKE } from './icons';
import styles from './ListRow.module.css';

interface Props {
  icon?: LucideIcon;
  label: string;
  onClick?: () => void;
  /** Right side instead of the chevron, e.g. a Toggle; the row is then not a button. */
  trailing?: ReactNode;
}

/** 56 px glass row of the cabinet lists (spec v2 §5). */
export function ListRow({ icon: Icon, label, onClick, trailing }: Props) {
  const content = (
    <>
      {Icon ? <Icon size={20} strokeWidth={ICON_STROKE} className={styles.icon} aria-hidden="true" /> : null}
      <span className={styles.label}>{label}</span>
      {trailing ?? <ChevronRight size={20} strokeWidth={ICON_STROKE} className={styles.chevron} aria-hidden="true" />}
    </>
  );
  if (trailing) return <div className={`glass ${styles.row}`}>{content}</div>;
  return (
    <button type="button" className={`glass ${styles.row} ${styles.button}`} onClick={onClick}>
      {content}
    </button>
  );
}
