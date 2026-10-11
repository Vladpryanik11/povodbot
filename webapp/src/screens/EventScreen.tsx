import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useReducer, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useApi } from '../api/ApiProvider';
import { ApiError } from '../api/AppApi';
import type { EventDetail } from '../api/types';
import { cartItems, cartReducer, cartTotal, fitCart, type CartState } from '../checkout/cart';
import { formatPrice, seatsLabel, ticketsLabel } from '../lib/format';
import { ACTIVE_ORDER_KEY } from '../start';
import { useBackButton, useMainButton, useTg } from '../telegram/hooks';
import { Dialog } from '../ui/Dialog';
import { EmptyState } from '../ui/EmptyState';
import { AttendeesStack } from '../ui/AttendeesStack';
import { ErrorState } from '../ui/ErrorState';
import { useGlow } from '../ui/Glow';
import { Pill } from '../ui/Pill';
import { PosterHeader } from '../ui/PosterHeader';
import { Skeleton } from '../ui/Skeleton';
import { Stepper } from '../ui/Stepper';
import { useEventColor } from '../ui/useEventColor';
import styles from './EventScreen.module.css';

type Problem =
  | { kind: 'active'; orderId: string; eventTitle: string }
  | { kind: 'seats'; seatsLeft: number }
  | { kind: 'network' }
  | { kind: 'closed' };

/** The guest's evening screen. With `preview` it shows the owner's unsaved evening: nothing loads, nothing is bought. */
export function EventScreen({ preview }: { preview?: EventDetail } = {}) {
  const { id = '' } = useParams();
  const api = useApi();
  const tg = useTg();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const event = useQuery({ queryKey: ['event', id], queryFn: () => api.event(id), enabled: !preview });
  const detail = preview ?? event.data;
  const [cart, dispatch] = useReducer(cartReducer, {} as CartState);
  const [submitting, setSubmitting] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const inFlight = useRef(false);
  const ticketsRef = useRef<HTMLElement>(null);
  const color = useEventColor(detail);
  useGlow(color);

  const goBack = () => navigate(-1);
  useBackButton(goBack);

  const offers = detail?.ticketTypes ?? [];
  const total = cartTotal(cart, offers);
  const soldOut = detail?.soldOut ?? false;

  const pay = async (items = cartItems(cart)) => {
    if (preview || inFlight.current || !event.data) return;
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
      } else if (error instanceof ApiError && error.code === 'sales_closed') {
        setProblem({ kind: 'closed' });
      } else {
        setProblem({ kind: 'network' });
      }
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  };

  const toTickets = () => {
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    ticketsRef.current?.scrollIntoView?.({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  };

  const bar =
    detail
      ? soldOut
        ? { text: 'Мест нет', enabled: false, progress: false, onClick: () => undefined }
        : total.count === 0
          ? { text: 'Купить', enabled: true, progress: false, summary: `от ${formatPrice(detail.minPriceKopecks)}`, onClick: toTickets }
          : {
              text: 'Купить',
              enabled: !submitting,
              progress: submitting,
              summary: `${ticketsLabel(total.count)} · ${formatPrice(total.kopecks)}`,
              onClick: () => void pay(),
            }
      : null;
  // The preview shows the guest's bar as is, but it takes no tap.
  useMainButton(bar && preview ? { ...bar, enabled: false, progress: false } : bar);

  if (!preview && event.error instanceof ApiError && event.error.code === 'not_found') {
    return (
      <EmptyState
        title="Вечер не найден"
        text="Возможно, он уже прошёл. Загляни на главную — там есть другие вечера."
        action={{ label: 'На главную', onClick: () => navigate('/', { replace: true }) }}
      />
    );
  }
  if (!preview && event.isError) {
    return (
      <ErrorState
        title="Нет связи"
        text="Проверь интернет и попробуй ещё раз."
        actionLabel="Повторить"
        onAction={() => void event.refetch()}
      />
    );
  }
  if (!detail) {
    return (
      <div className={styles.loading}>
        <Skeleton height={200} />
        <Skeleton height={120} />
      </div>
    );
  }

  const data = detail;

  return (
    <main className={styles.page}>
      <PosterHeader event={data} color={color ?? '#000000'} onBack={goBack} />
      <div className={styles.body}>
        <div className={styles.pills}>
          {preview ? <Pill tone="glass">Так увидит гость</Pill> : null}
          <span className={styles.pill}>18+</span>
          {data.attendees.count > 0 ? (
            <span className={styles.pill}>
              <AttendeesStack count={data.attendees.count} avatars={data.attendees.avatars} />
            </span>
          ) : null}
        </div>

        <section className={styles.section} aria-labelledby="about">
          <h2 id="about" className={`t-h2 ${styles.sectionTitle}`}>
            О вечере
          </h2>
          <p className={styles.description}>{data.description}</p>
        </section>

        <section className={styles.section} aria-labelledby="where">
          <h2 id="where" className={`t-h2 ${styles.sectionTitle}`}>
            Где
          </h2>
          {data.address ? (
            <p className={styles.place}>
              {data.address}
              {data.mapUrl ? (
                <a href={data.mapUrl} className={styles.route} onClick={(e) => (e.preventDefault(), tg.openLink(data.mapUrl!))}>
                  Построить маршрут
                </a>
              ) : null}
            </p>
          ) : (
            <p className={styles.place}>Адрес пришлём в бот</p>
          )}
        </section>

        <section ref={ticketsRef} className={`${styles.section} ${styles.tickets}`} aria-labelledby="tickets">
          <h2 id="tickets" className={`t-h2 ${styles.sectionTitle}`}>
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
          <p className={styles.refund}>Полный возврат — если до вечера больше 3 дней.</p>
        </section>
      </div>

      {problem?.kind === 'active' ? (
        <Dialog
          title="У тебя уже есть бронь"
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
          text="Проверь интернет. Места пока никто не забронировал."
          confirmLabel="Повторить"
          cancelLabel="Закрыть"
          onConfirm={() => {
            setProblem(null);
            void pay();
          }}
          onCancel={() => setProblem(null)}
        />
      ) : null}
      {problem?.kind === 'closed' ? (
        <Dialog
          title="Билеты — в чате бота"
          text="Здесь покупка появится скоро. Пока купи в чате: Афиша → вечер → билет."
          confirmLabel="Понятно"
          cancelLabel="К афише"
          onConfirm={() => setProblem(null)}
          onCancel={() => navigate('/')}
        />
      ) : null}
    </main>
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
        text="Пока шёл выбор, места закончились. Загляни на главную — там есть другие вечера."
        confirmLabel="На главную"
        cancelLabel="Закрыть"
        onConfirm={onAfisha}
        onCancel={onClose}
      />
    );
  }
  return (
    <Dialog
      title="Мест стало меньше"
      text={`Пока шёл выбор, ${seatsLabel(left)}. Берём ${left}?`}
      confirmLabel={`Берём ${left}`}
      cancelLabel="Изменить"
      onConfirm={() => onTake(fitCart(cart, event.ticketTypes, left))}
      onCancel={onClose}
    />
  );
}
