import { useQuery, useQueryClient } from '@tanstack/react-query';
import { CalendarDays, Clock, MapPin, Users } from 'lucide-react';
import { useReducer, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useApi } from '../api/ApiProvider';
import { ApiError } from '../api/AppApi';
import type { EventDetail } from '../api/types';
import { cartItems, cartReducer, cartTotal, fitCart, type CartState } from '../checkout/cart';
import { formatDate, formatPrice, formatTime, plural, seatsLabel, ticketsLabel } from '../lib/format';
import { usePollVote } from '../polls/usePollVote';
import { ACTIVE_ORDER_KEY } from '../start';
import { useBackButton, useMainButton, useTg } from '../telegram/hooks';
import { Dialog } from '../ui/Dialog';
import { EmptyState } from '../ui/EmptyState';
import { ErrorState } from '../ui/ErrorState';
import { ICON_STROKE } from '../ui/icons';
import { PhotoHeader } from '../ui/PhotoHeader';
import { PollCard } from '../ui/PollCard';
import { Skeleton } from '../ui/Skeleton';
import { Stepper } from '../ui/Stepper';
import styles from './EventScreen.module.css';

const LONG_TITLE = 28;

type Problem =
  | { kind: 'active'; orderId: string; eventTitle: string }
  | { kind: 'seats'; seatsLeft: number }
  | { kind: 'network' };

export function EventScreen() {
  const { id = '' } = useParams();
  const api = useApi();
  const tg = useTg();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const event = useQuery({ queryKey: ['event', id], queryFn: () => api.event(id) });
  const directions = useQuery({ queryKey: ['directions'], queryFn: () => api.directions() });
  const [cart, dispatch] = useReducer(cartReducer, {} as CartState);
  const [submitting, setSubmitting] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const inFlight = useRef(false);
  const { vote, closedNow, failed, pending } = usePollVote();

  const goBack = () => navigate(-1);
  useBackButton(goBack);

  const offers = event.data?.ticketTypes ?? [];
  const total = cartTotal(cart, offers);
  const soldOut = event.data?.soldOut ?? false;

  const pay = async (items = cartItems(cart)) => {
    if (inFlight.current || !event.data) return;
    inFlight.current = true;
    setSubmitting(true);
    try {
      const order = await api.createOrder(event.data.id, items);
      tg.closingConfirmation(true);
      await tg.storage.set(ACTIVE_ORDER_KEY, order.id);
      void queryClient.invalidateQueries({ queryKey: ['me'] });
      navigate(`/order/${order.id}`);
      tg.openLink(order.paymentUrl);
    } catch (error) {
      if (error instanceof ApiError && error.code === 'active_order_exists') {
        setProblem({ kind: 'active', orderId: error.data.orderId ?? '', eventTitle: error.data.eventTitle ?? '' });
      } else if (error instanceof ApiError && error.code === 'not_enough_seats') {
        tg.haptic.notify('warning');
        setProblem({ kind: 'seats', seatsLeft: error.data.seatsLeft ?? 0 });
      } else {
        setProblem({ kind: 'network' });
      }
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  };

  useMainButton(
    event.data
      ? soldOut
        ? { text: 'Мест нет', enabled: false, progress: false, onClick: () => undefined }
        : total.count === 0
          ? { text: 'Выберите билеты', enabled: false, progress: false, onClick: () => undefined }
          : { text: `Оплатить ${formatPrice(total.kopecks)}`, enabled: !submitting, progress: submitting, onClick: () => void pay() }
      : null,
  );

  if (event.error instanceof ApiError && event.error.code === 'not_found') {
    return (
      <EmptyState
        title="Вечер не найден"
        text="Возможно, он уже прошёл. Загляните в афишу — там есть другие вечера."
        action={{ label: 'К афише', onClick: () => navigate('/', { replace: true }) }}
      />
    );
  }
  if (event.isError) {
    return (
      <ErrorState
        title="Нет связи"
        text="Проверьте интернет и попробуйте ещё раз."
        actionLabel="Повторить"
        onAction={() => void event.refetch()}
      />
    );
  }
  if (!event.data) {
    return (
      <div className={styles.loading}>
        <Skeleton height={200} />
        <Skeleton height={120} />
      </div>
    );
  }

  const data = event.data;
  const icon = directions.data?.find((d) => d.id === data.directionId)?.icon ?? 'film';

  return (
    <main className={styles.page}>
      <PhotoHeader poster={data.poster} title={data.title} icon={icon} onBack={tg.isTelegram ? undefined : goBack} />
      <div className={styles.body}>
        <h1
          className={`t-h1 ${styles.title} ${data.title.length > LONG_TITLE ? styles.titleLong : ''}`}
          data-long={data.title.length > LONG_TITLE ? 'true' : 'false'}
        >
          {data.title}
        </h1>
        <Stats event={data} />
        <p className={styles.place}>
          <MapPin size={20} strokeWidth={ICON_STROKE} aria-hidden="true" />
          {data.address ? (
            <span>
              {data.address}
              {data.mapUrl ? (
                <>
                  {' · '}
                  <a href={data.mapUrl} onClick={(e) => (e.preventDefault(), tg.openLink(data.mapUrl!))}>
                    На карте
                  </a>
                </>
              ) : null}
            </span>
          ) : (
            <span>Место пока уточняется. Напишем в боте, как только определимся.</span>
          )}
        </p>

        <section className={styles.section} aria-labelledby="about">
          <h2 id="about" className={`t-h3 ${styles.sectionTitle}`}>
            О вечере
          </h2>
          <p className={styles.description}>{data.description}</p>
        </section>

        {data.poll ? (
          <PollCard
            poll={data.poll}
            closedNow={closedNow.has(data.poll.id)}
            failed={failed.has(data.poll.id)}
            busy={pending === data.poll.id}
            onVote={(optionId) => void vote(data.poll!, optionId)}
          />
        ) : null}

        <section className={`${styles.section} ${styles.tickets}`} aria-labelledby="tickets">
          <h2 id="tickets" className={`t-h3 ${styles.sectionTitle}`}>
            Билеты
          </h2>
          {data.ticketTypes.map((offer) => (
            <div key={offer.id} className={styles.offer}>
              <div>
                <div className={styles.offerName}>{offer.name}</div>
                <div className={`t-price ${styles.offerPrice}`}>{formatPrice(offer.priceKopecks)}</div>
                <div className={styles.offerSeats}>{seatsLabel(offer.seatsLeft)}</div>
              </div>
              <Stepper
                value={cart[offer.id] ?? 0}
                max={offer.seatsLeft}
                label={offer.name}
                onChange={(next) => {
                  tg.haptic.impact('light');
                  dispatch({ type: next > (cart[offer.id] ?? 0) ? 'inc' : 'dec', ticketTypeId: offer.id, max: offer.seatsLeft });
                }}
              />
            </div>
          ))}
          {total.count > 0 ? (
            <p className={`t-price ${styles.summary}`} aria-live="polite">
              {ticketsLabel(total.count)} · {formatPrice(total.kopecks)}
            </p>
          ) : null}
          <p className={styles.refund}>Полный возврат — если до вечера больше 3 дней.</p>
        </section>
      </div>

      {problem?.kind === 'active' ? (
        <Dialog
          title="У вас уже есть бронь"
          text={`Бронь на «${problem.eventTitle}» ждёт оплаты. Продолжить оплату или отменить?`}
          confirmLabel="Продолжить"
          cancelLabel="Не сейчас"
          onConfirm={() => navigate(`/order/${problem.orderId}`)}
          onCancel={() => setProblem(null)}
        />
      ) : null}
      {problem?.kind === 'seats' ? <SeatsDialog problem={problem} cart={cart} event={data} onClose={() => setProblem(null)} onTake={(next) => {
        dispatch({ type: 'replace', cart: next });
        setProblem(null);
        void pay(cartItems(next));
      }} onAfisha={() => navigate('/')} /> : null}
      {problem?.kind === 'network' ? (
        <Dialog
          title="Нет связи"
          text="Проверьте интернет. Места пока никто не забронировал."
          confirmLabel="Повторить"
          cancelLabel="Закрыть"
          onConfirm={() => {
            setProblem(null);
            void pay();
          }}
          onCancel={() => setProblem(null)}
        />
      ) : null}
    </main>
  );
}

function Stats({ event }: { event: EventDetail }) {
  return (
    <ul className={styles.stats}>
      <li>
        <CalendarDays size={20} strokeWidth={ICON_STROKE} className={styles.iconAccent} aria-hidden="true" />
        {formatDate(event.startsAt, event.timezone)}
      </li>
      <li>
        <Clock size={20} strokeWidth={ICON_STROKE} className={styles.iconViolet} aria-hidden="true" />
        {formatTime(event.startsAt, event.timezone)}
      </li>
      <li>
        <Users size={20} strokeWidth={ICON_STROKE} className={styles.iconMint} aria-hidden="true" />
        {event.soldOut ? 'мест нет' : `${event.seatsLeft} ${plural(event.seatsLeft, ['место', 'места', 'мест'])}`}
      </li>
    </ul>
  );
}

function SeatsDialog({
  problem,
  cart,
  event,
  onClose,
  onTake,
  onAfisha,
}: {
  problem: { seatsLeft: number };
  cart: CartState;
  event: EventDetail;
  onClose: () => void;
  onTake: (cart: CartState) => void;
  onAfisha: () => void;
}) {
  const left = problem.seatsLeft;
  if (left <= 0) {
    return (
      <Dialog
        title="Мест не осталось"
        text="Пока вы выбирали, места закончились. Загляните в афишу — там есть другие вечера."
        confirmLabel="К афише"
        cancelLabel="Закрыть"
        onConfirm={onAfisha}
        onCancel={onClose}
      />
    );
  }
  return (
    <Dialog
      title="Мест стало меньше"
      text={`Пока вы выбирали, ${seatsLabel(left)}. Взять ${ticketsLabel(left)}?`}
      confirmLabel={`Взять ${left}`}
      cancelLabel="Изменить"
      onConfirm={() => onTake(fitCart(cart, event.ticketTypes, left))}
      onCancel={onClose}
    />
  );
}
