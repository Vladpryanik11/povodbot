import { useQuery } from '@tanstack/react-query';
import { CalendarDays, Sparkles, Timer } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useApi } from '../api/ApiProvider';
import { ApiError } from '../api/AppApi';
import type { Direction, EventCard, Order } from '../api/types';
import { useCountdown } from '../checkout/useCountdown';
import { formatDateTime, formatPrice, seatsLabel } from '../lib/format';
import { useTg } from '../telegram/hooks';
import { DirectionTile } from '../ui/DirectionTile';
import { EmptyState } from '../ui/EmptyState';
import { ErrorState } from '../ui/ErrorState';
import { ICON_STROKE } from '../ui/icons';
import { Pill } from '../ui/Pill';
import { Poster } from '../ui/Poster';
import { Skeleton } from '../ui/Skeleton';
import styles from './Afisha.module.css';

const LONG_TITLE = 28;

export function Afisha() {
  const api = useApi();
  const tg = useTg();
  const [directionId, setDirectionId] = useState<string | undefined>();
  const directions = useQuery({ queryKey: ['directions'], queryFn: () => api.directions() });
  const events = useQuery({ queryKey: ['events', directionId ?? 'all'], queryFn: () => api.events(directionId) });
  const me = useQuery({ queryKey: ['me'], queryFn: () => api.me() });

  const pick = (id: string | undefined) => {
    tg.haptic.selection();
    setDirectionId(id);
  };

  const iconOf = (event: EventCard) =>
    directions.data?.find((d) => d.id === event.directionId)?.icon ?? 'film';

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <span className={`t-h2 ${styles.brand}`}>Повод</span>
      </header>

      {me.data?.activeOrder ? <ReservationPlaque order={me.data.activeOrder} /> : null}

      {events.isError ? (
        <ErrorState
          title="Нет связи"
          text={
            events.error instanceof ApiError && events.error.code === 'network'
              ? 'Проверьте интернет. Оплаченные билеты никуда не денутся.'
              : 'Не получилось загрузить афишу. Попробуйте ещё раз.'
          }
          actionLabel="Повторить"
          onAction={() => void events.refetch()}
        />
      ) : events.isPending ? (
        <div className={styles.loading}>
          <Skeleton height={200} />
          <Skeleton height={72} />
        </div>
      ) : (
        <>
          <DirectionRow directions={directions.data ?? []} selected={directionId} onPick={pick} />
          {events.data.length === 0 ? (
            <EmptyState
              icon={CalendarDays}
              title="Пока тихо"
              text="Новых вечеров нет. Как появятся, напишем в боте."
            />
          ) : (
            <>
              <Hero event={events.data[0]} icon={iconOf(events.data[0])} />
              {events.data.length > 1 ? (
                <section className={styles.section} aria-labelledby="soon">
                  <h2 id="soon" className={`t-h3 ${styles.sectionTitle}`}>
                    Скоро
                  </h2>
                  <div className={styles.grid}>
                    {events.data.slice(1).map((event) => (
                      <EventTile key={event.id} event={event} icon={iconOf(event)} />
                    ))}
                  </div>
                </section>
              ) : null}
            </>
          )}
        </>
      )}
    </main>
  );
}

function DirectionRow({
  directions,
  selected,
  onPick,
}: {
  directions: Direction[];
  selected: string | undefined;
  onPick: (id: string | undefined) => void;
}) {
  if (directions.length === 0) return null;
  return (
    <div className={styles.directions} role="group" aria-label="Направления">
      <DirectionTile
        direction={{ title: 'Все', icon: 'party' }}
        iconOverride={Sparkles}
        selected={selected === undefined}
        onSelect={() => onPick(undefined)}
      />
      {directions.map((direction) => (
        <DirectionTile
          key={direction.id}
          direction={direction}
          selected={selected === direction.id}
          onSelect={() => onPick(direction.id)}
        />
      ))}
    </div>
  );
}

function Title({ text, className }: { text: string; className: string }) {
  const long = text.length > LONG_TITLE;
  return (
    <span className={`${className} ${long ? styles.titleLong : ''}`} data-long={long ? 'true' : 'false'}>
      {text}
    </span>
  );
}

function Hero({ event, icon }: { event: EventCard; icon: Direction['icon'] }) {
  return (
    <Link to={`/events/${event.id}`} className={styles.heroLink} data-sold-out={event.soldOut ? 'true' : 'false'}>
      <Poster poster={event.poster} title={event.title} ratio="2:1" icon={icon} className={styles.hero}>
        <div data-testid="hero" className={styles.heroInner}>
          <div>
            <Pill tone="accent">{formatDateTime(event.startsAt, event.timezone)}</Pill>
          </div>
          <div className={styles.heroBottom}>
            <Title text={event.title} className={`t-h1 ${styles.heroTitle}`} />
            <div className={styles.pills}>
              <Pill tone="glass">{seatsLabel(event.seatsLeft)}</Pill>
              {!event.soldOut ? <Pill tone="glass">от {formatPrice(event.minPriceKopecks)}</Pill> : null}
            </div>
          </div>
        </div>
      </Poster>
    </Link>
  );
}

function EventTile({ event, icon }: { event: EventCard; icon: Direction['icon'] }) {
  return (
    <Link
      to={`/events/${event.id}`}
      className={`${styles.tile} ${event.soldOut ? styles.soldOut : ''}`}
      data-sold-out={event.soldOut ? 'true' : 'false'}
    >
      <Poster poster={event.poster} title={event.title} ratio="4:5" icon={icon}>
        <span className={styles.tileDate}>{formatDateTime(event.startsAt, event.timezone)}</span>
        <span className={styles.tileBottom}>
          <Title text={event.title} className={`t-h3 ${styles.tileTitle}`} />
          <span className={styles.tileMeta}>
            {event.soldOut ? 'мест нет' : `от ${formatPrice(event.minPriceKopecks)}`}
          </span>
        </span>
      </Poster>
    </Link>
  );
}

function ReservationPlaque({ order }: { order: Order }) {
  const { left } = useCountdown(order.expiresAt);
  return (
    <Link to={`/order/${order.id}`} className={`glass ${styles.plaque}`}>
      <Timer size={20} strokeWidth={ICON_STROKE} aria-hidden="true" />
      <span>Бронь ждёт оплаты · {left}</span>
    </Link>
  );
}
