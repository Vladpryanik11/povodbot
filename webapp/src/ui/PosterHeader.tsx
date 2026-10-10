import { ArrowLeft } from 'lucide-react';
import type { EventCard } from '../api/types';
import { useDirections } from '../api/useDirections';
import { formatDateTime } from '../lib/format';
import { FavButton } from './FavButton';
import { ICON_STROKE } from './icons';
import { PosterImage } from './PosterImage';
import styles from './PosterHeader.module.css';

const LONG_TITLE = 28;
/** The club is 18+; events carry no age field yet. */
const AGE = '18+';

interface Props {
  event: EventCard;
  /** Poster colour, for the block shown when there is no usable photo. */
  color: string;
  onBack: () => void;
}

/** Full-width 4:5 poster fading into black, with back and heart on glass and the title on the photo (spec v2 §5). */
export function PosterHeader({ event, color, onBack }: Props) {
  const directions = useDirections();
  const direction = directions.find((d) => d.id === event.directionId);
  const long = event.title.length > LONG_TITLE;
  return (
    <header className={styles.header} data-sold-out={event.soldOut || undefined}>
      <PosterImage poster={event.poster} color={color} icon={direction?.icon ?? 'film'} />
      <div className={styles.scrim} />
      <div className={styles.top}>
        <button type="button" className={`glass ${styles.back}`} aria-label="Назад" onClick={onBack}>
          <ArrowLeft size={20} strokeWidth={ICON_STROKE} aria-hidden="true" />
        </button>
        <FavButton eventId={event.id} size={40} />
      </div>
      <div className={styles.bottom}>
        <span className={styles.meta}>{direction ? `${direction.title} · ${AGE}` : AGE}</span>
        <h1 className={`t-h1 ${styles.title} ${long ? styles.titleLong : ''}`} data-long={long ? 'true' : 'false'}>
          {event.title}
        </h1>
        <p className={styles.when}>{formatDateTime(event.startsAt, event.timezone)}</p>
      </div>
    </header>
  );
}
