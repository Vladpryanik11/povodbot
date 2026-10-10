import type { CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import type { EventCard } from '../api/types';
import { useDirections } from '../api/useDirections';
import { formatDateTime } from '../lib/format';
import { eventColor } from '../lib/posterColor';
import { FavButton } from './FavButton';
import { PosterImage } from './PosterImage';
import { PosterStatus } from './StatusPill';
import styles from './PosterRow.module.css';

type Variant = 'wide' | 'tall';

/** One poster: wide 16:9 with the text on the photo, tall 4:5 with the text underneath (spec v2 §5). */
export function PosterCard({ event, variant, now = Date.now() }: { event: EventCard; variant: Variant; now?: number }) {
  const directions = useDirections();
  const icon = directions.find((d) => d.id === event.directionId)?.icon ?? 'film';
  const color = eventColor(event);
  const when = formatDateTime(event.startsAt, event.timezone);
  return (
    <div className={`${styles.card} ${styles[variant]}`} style={{ '--poster': color } as CSSProperties}>
      <Link to={`/events/${event.id}`} className={styles.link} data-sold-out={event.soldOut || undefined}>
        <div className={styles.poster}>
          <PosterImage poster={event.poster} color={color} icon={icon} />
          {variant === 'wide' ? <div className={styles.scrim} /> : null}
          <div className={styles.status}><PosterStatus event={event} now={now} /></div>
          {variant === 'wide' ? (
            <div className={styles.onPhoto}>
              <span className={`${styles.name} t-h3`}>{event.title}</span>
              <span className={styles.when}>{when}</span>
            </div>
          ) : null}
        </div>
        {variant === 'tall' ? (
          <div className={styles.under}>
            <span className={`${styles.name} t-h3`}>{event.title}</span>
            <span className="t-meta">{when}</span>
          </div>
        ) : null}
      </Link>
      <div className={styles.fav}>
        <FavButton eventId={event.id} />
      </div>
    </div>
  );
}

/** A titled horizontal row of posters; the edge of the next one peeks in. */
export function PosterRow({ title, variant, events, now }: { title: string; variant: Variant; events: EventCard[]; now?: number }) {
  if (events.length === 0) return null;
  const id = `row-${variant}`;
  return (
    <section className={styles.row} aria-labelledby={id}>
      <h2 id={id} className={`${styles.heading} t-h2`}>
        {title}
      </h2>
      <ul className={styles.track}>
        {events.map((event) => (
          <li key={event.id} className={styles[`${variant}Item`]}>
            <PosterCard event={event} variant={variant} now={now} />
          </li>
        ))}
      </ul>
    </section>
  );
}
