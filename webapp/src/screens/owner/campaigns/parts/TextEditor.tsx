import { useRef, useState } from 'react';
import { CMSG } from '../../../../api/campaigns/messages';
import { markupToHtml, telegramLength } from '../../../../owner/campaigns/text';
import formStyles from '../../OwnerEventForm.module.css';
import styles from './parts.module.css';

interface Props {
  id: string;
  /** Editor markup: **bold**, __italic__, [label](https://…). */
  value: string;
  onChange(next: string): void;
  limit: number;
  error?: string;
}

const URL_OK = /^https:\/\/[^\s)"<>]+$/;

/** The message text with bold, italic and link helpers, and a counter that measures like Telegram. */
export function TextEditor({ id, value, onChange, limit, error }: Props) {
  const area = useRef<HTMLTextAreaElement>(null);
  const [link, setLink] = useState<{ start: number; end: number; url: string; error: string | null } | null>(null);
  const length = telegramLength(markupToHtml(value));
  const over = length > limit;
  const shown = error ?? (over ? CMSG.tooLong : undefined);
  const errorId = `${id}-error`;

  const selection = () => ({
    start: area.current?.selectionStart ?? value.length,
    end: area.current?.selectionEnd ?? value.length,
  });

  const replace = (start: number, end: number, text: string, caret: [number, number]) => {
    onChange(value.slice(0, start) + text + value.slice(end));
    requestAnimationFrame(() => {
      area.current?.focus();
      area.current?.setSelectionRange(start + caret[0], start + caret[1]);
    });
  };

  const wrap = (marker: string) => {
    const { start, end } = selection();
    const inner = value.slice(start, end);
    replace(start, end, `${marker}${inner}${marker}`, [marker.length, marker.length + inner.length]);
  };

  const insertLink = () => {
    if (!link) return;
    const url = link.url.trim();
    if (!URL_OK.test(url)) {
      setLink({ ...link, error: CMSG.httpsOnly });
      return;
    }
    const label = value.slice(link.start, link.end).replace(/[\]\n]/g, ' ').trim() || 'ссылка';
    const text = `[${label}](${url})`;
    replace(link.start, link.end, text, [text.length, text.length]);
    setLink(null);
  };

  return (
    <div className={formStyles.field}>
      <label htmlFor={id} className={formStyles.label}>
        Текст
      </label>
      <div className={styles.toolbar}>
        <button type="button" className={`glass ${styles.tool}`} aria-label="Жирный" onClick={() => wrap('**')}>
          Ж
        </button>
        <button type="button" className={`glass ${styles.tool}`} aria-label="Курсив" onClick={() => wrap('__')}>
          <i>К</i>
        </button>
        <button
          type="button"
          className={`glass ${styles.tool}`}
          onClick={() => setLink({ ...selection(), url: 'https://', error: null })}
        >
          Ссылка
        </button>
      </div>
      {link ? (
        <div className={styles.linkRow}>
          <label htmlFor={`${id}-url`} className={formStyles.label}>
            Адрес ссылки
          </label>
          <input
            id={`${id}-url`}
            className={formStyles.input}
            type="url"
            inputMode="url"
            value={link.url}
            aria-invalid={link.error ? true : undefined}
            onChange={(e) => setLink({ ...link, url: e.target.value, error: null })}
          />
          {link.error ? <p className={formStyles.error}>{link.error}</p> : null}
          <div className={styles.linkActions}>
            <button type="button" className={`glass ${styles.tool}`} onClick={insertLink}>
              Вставить
            </button>
            <button type="button" className={`glass ${styles.tool}`} onClick={() => setLink(null)}>
              Отмена
            </button>
          </div>
        </div>
      ) : null}
      <textarea
        ref={area}
        id={id}
        className={formStyles.input}
        rows={6}
        value={value}
        aria-describedby={shown ? errorId : undefined}
        aria-invalid={shown ? true : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
      <p className={`${styles.counter} ${over ? styles.over : ''}`}>{`${length} / ${limit}`}</p>
      {shown ? (
        <p id={errorId} className={formStyles.error}>
          {shown}
        </p>
      ) : null}
    </div>
  );
}
