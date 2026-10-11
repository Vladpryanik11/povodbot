import type { CampaignButton } from '../../../../api/campaigns/types';
import { markupToHtml } from '../../../../owner/campaigns/text';
import styles from './parts.module.css';

interface Props {
  /** Editor markup; it is escaped here, so nothing but <b>, <i> and https links reaches the DOM. */
  markup: string;
  imageUrl: string | null;
  buttons: CampaignButton[];
}

/** How the message will look in Telegram. */
export function MessageBubble({ markup, imageUrl, buttons }: Props) {
  return (
    <figure className={styles.preview} aria-label="Предпросмотр">
      <div className={styles.bubble}>
        {imageUrl ? <img className={styles.bubbleImage} src={imageUrl} alt="" /> : null}
        {markup.trim() ? (
          <p
            className={styles.bubbleText}
            // A preview: links do not leave the app.
            onClick={(e) => {
              if ((e.target as HTMLElement).closest('a')) e.preventDefault();
            }}
            dangerouslySetInnerHTML={{ __html: markupToHtml(markup) }}
          />
        ) : (
          <p className={`${styles.bubbleText} ${styles.placeholder}`}>Здесь будет текст</p>
        )}
      </div>
      {buttons.length ? (
        <div className={styles.keys}>
          {buttons.map((b, i) => (
            <span key={i} className={styles.key}>
              {b.label}
            </span>
          ))}
        </div>
      ) : null}
    </figure>
  );
}
