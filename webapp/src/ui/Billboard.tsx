import { useEffect, useState, type CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import type { EventCard } from '../api/types';
import { useDirections } from '../api/useDirections';
import { billboardSubtitle } from '../lib/format';
import { eventColor, extractPosterColor } from '../lib/posterColor';
import { PosterImage } from './PosterImage';
import { PosterStatus } from './StatusPill';
import styles from './Billboard.module.css';

const SLIDES = 3;
const AUTOPLAY_MS = 6000;
const LONG_TITLE = 28;
/** The club is 18+; events carry no age field yet. */
const AGE = '18+';

type Props = { events: EventCard[]; now: number };

/** Hero of the home screen: up to three nearest evenings, one at a time, moving on every 6 s (spec v2 §5). */
export function Billboard({ events, now }: Props) {
  const slides = events.slice(0, SLIDES);
  const directions = useDirections();
  const [index, setIndex] = useState(0);
  const [held, setHeld] = useState(false);
  const [picked, setPicked] = useState<Record<string, string>>({});
  const current = slides[Math.min(index, slides.length - 1)];
  const ids = slides.map((e) => e.id).join();

  useEffect(() => setIndex(0), [ids]);

  useEffect(() => {
    if (held || slides.length < 2) return;
    const timer = setTimeout(() => setIndex((i) => (i + 1) % slides.length), AUTOPLAY_MS);
    return () => clearTimeout(timer);
  }, [held, index, slides.length]);

  useEffect(() => {
    if (!current || current.accentColor || !current.poster) return;
    let live = true;
    void extractPosterColor(current.poster.url).then((hex) => {
      if (live && hex) setPicked((p) => ({ ...p, [current.id]: hex }));
    });
    return () => {
      live = false;
    };
    // Keyed by id: a refetch hands over new objects for the same slide.
  }, [current?.id]);

  if (!current) return null;

  return (
    <section
      className={styles.billboard}
      aria-label="Главное"
      aria-roledescription="карусель"
      onPointerDown={() => setHeld(true)}
      onPointerUp={() => setHeld(false)}
      onPointerCancel={() => setHeld(false)}
      onPointerLeave={() => setHeld(false)}
    >
      <div className={styles.frame}>
        {slides.map((event, i) => {
          const isCurrent = event.id === current.id;
          const direction = directions.find((d) => d.id === event.directionId);
          const long = event.title.length > LONG_TITLE;
          const color = eventColor(event, picked[event.id]);
          return (
            <Link
              key={event.id}
              to={`/events/${event.id}`}
              className={styles.slide}
              data-current={isCurrent || undefined}
              data-sold-out={event.soldOut || undefined}
              aria-hidden={isCurrent ? undefined : true}
              tabIndex={isCurrent ? undefined : -1}
              style={{ '--poster': color } as CSSProperties}
              aria-roledescription="слайд"
              aria-label={`${i + 1} из ${slides.length}: ${event.title}`}
            >
              <PosterImage poster={event.poster} color={color} icon={direction?.icon ?? 'film'} />
              <div className={styles.scrim} />
              <div className={styles.top}>
                <span className={styles.meta}>{direction ? `${direction.title} · ${AGE}` : AGE}</span>
                <PosterStatus event={event} now={now} />
              </div>
              <div className={styles.bottom}>
                <p className={styles.kicker}>{billboardSubtitle(event.startsAt, event.timezone, now)}</p>
                <h2 className={styles.title} data-long={long || undefined}>
                  {event.title}
                </h2>
              </div>
            </Link>
          );
        })}
      </div>
      {slides.length > 1 ? (
        <div className={styles.dots} role="tablist" aria-label="Слайды">
          {slides.map((event, i) => (
            <button
              key={event.id}
              type="button"
              role="tab"
              aria-selected={event.id === current.id}
              aria-label={`Слайд ${i + 1} из ${slides.length}`}
              className={styles.dot}
              onClick={() => setIndex(i)}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}
