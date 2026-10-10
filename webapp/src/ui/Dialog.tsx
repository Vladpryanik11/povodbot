import { useEffect, useId, useRef } from 'react';
import { Button } from './Button';
import styles from './Dialog.module.css';

interface DialogProps {
  title: string;
  text: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function Dialog({ title, text, confirmLabel, cancelLabel, onConfirm, onCancel }: DialogProps) {
  const titleId = useId();
  const confirmRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    confirmRef.current?.querySelector('button')?.focus();
  }, []);
  return (
    <div className={styles.overlay} onClick={onCancel}>
      <div
        className={styles.sheet}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => event.key === 'Escape' && onCancel()}
      >
        <h2 id={titleId} className={styles.title}>
          {title}
        </h2>
        <p className={styles.text}>{text}</p>
        <div className={styles.actions} ref={confirmRef}>
          <Button wide onClick={onConfirm}>
            {confirmLabel}
          </Button>
          <Button wide variant="outline" onClick={onCancel}>
            {cancelLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
