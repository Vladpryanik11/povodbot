import { useQuery, useQueryClient } from '@tanstack/react-query';
import { CircleCheck, Hourglass, Landmark, TimerOff, TriangleAlert, type LucideIcon } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useApi } from '../api/ApiProvider';
import { ApiError } from '../api/AppApi';
import type { Order } from '../api/types';
import { formatLeft } from '../checkout/useCountdown';
import { formatDate, formatPrice, formatTime, plural, ticketsLabel } from '../lib/format';
import { ACTIVE_ORDER_KEY } from '../start';
import { useBackButton, useMainButton, useTg } from '../telegram/hooks';
import { ticketsQuery } from '../tickets/useTickets';
import { Button } from '../ui/Button';
import { Dialog } from '../ui/Dialog';
import { EmptyState } from '../ui/EmptyState';
import { ErrorState } from '../ui/ErrorState';
import { Skeleton } from '../ui/Skeleton';
import styles from './OrderScreen.module.css';

type View = 'waiting' | 'bank' | 'bankSlow' | 'paid' | 'failed' | 'expired' | 'cancelled' | 'late';

const BANK_PATIENCE_MS = 60_000;
const ANNOUNCE_AT_MINUTES = new Set([5, 2, 1, 0]);

function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}

function viewOf(order: Order, now: number, mountedAt: number): View {
  const left = Date.parse(order.expiresAt) - now;
  switch (order.status) {
    case 'pending':
      if (order.paymentUncertain) return now - mountedAt > BANK_PATIENCE_MS ? 'bankSlow' : 'bank';
      return left > 0 ? 'waiting' : 'expired';
    case 'failed':
      return left > 0 ? 'failed' : 'expired';
    case 'paid':
      return 'paid';
    case 'cancelled':
      return 'cancelled';
    case 'reconciliation':
      return 'late';
    default:
      return 'expired';
  }
}

export function OrderScreen() {
  const { id = '' } = useParams();
  const api = useApi();
  const tg = useTg();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const now = useNow();
  const [mountedAt] = useState(() => Date.now());
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const order = useQuery({
    queryKey: ['order', id],
    queryFn: () => api.order(id),
    // A failed attempt can still turn into a payment when the guest retries on the bank page.
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'pending' || status === 'failed' ? 3000 : false;
    },
  });

  const view = order.data ? viewOf(order.data, now, mountedAt) : null;
  const live = view === 'waiting' || view === 'bank' || view === 'bankSlow' || view === 'failed';

  useEffect(() => {
    if (!view) return;
    tg.closingConfirmation(view === 'waiting' || view === 'bank' || view === 'failed');
    if (view === 'paid') tg.haptic.notify('success');
    if (view === 'failed') tg.haptic.notify('error');
    if (view === 'expired') tg.haptic.notify('warning');
    if (view === 'paid') void queryClient.prefetchQuery(ticketsQuery(api));
    // The local clock ran out: ask the server once more before believing it.
    if (view === 'expired' && (order.data?.status === 'pending' || order.data?.status === 'failed')) {
      void order.refetch();
    }
    if (!live) {
      void tg.storage.set(ACTIVE_ORDER_KEY, '');
      void queryClient.invalidateQueries({ queryKey: ['me'] });
    }
    // Only the change of view matters here, not every tick of the clock.
  }, [view]);

  useBackButton(() => navigate(live ? '/' : '/tickets'));

  const data = order.data;
  const reopen = () => data && tg.openLink(data.paymentUrl);
  useMainButton(
    !data || !view
      ? null
      : view === 'waiting'
        ? { text: 'Открыть оплату снова', enabled: true, progress: false, onClick: reopen }
        : view === 'failed'
          ? { text: 'Попробовать снова', enabled: true, progress: false, onClick: reopen }
          : view === 'paid'
            ? { text: 'Показать билеты', enabled: true, progress: false, onClick: () => navigate('/tickets', { replace: true }) }
            : view === 'expired' || view === 'cancelled'
              ? { text: 'Выбрать заново', enabled: true, progress: false, onClick: () => navigate(`/events/${data.eventId}`, { replace: true }) }
              : view === 'bankSlow' || view === 'late'
                ? { text: 'К афише', enabled: true, progress: false, onClick: () => navigate('/', { replace: true }) }
                : null,
  );

  if (order.error instanceof ApiError && order.error.code === 'not_found') {
    return (
      <EmptyState
        title="Заказ не найден"
        text="Возможно, ссылка устарела. Билеты, если они есть, — во вкладке «Билеты»."
        action={{ label: 'К афише', onClick: () => navigate('/', { replace: true }) }}
      />
    );
  }
  if (order.isError) {
    return (
      <ErrorState
        title="Нет связи"
        text="Проверьте интернет. Оплаченные билеты никуда не денутся."
        actionLabel="Повторить"
        onAction={() => void order.refetch()}
      />
    );
  }
  if (!data || !view) {
    return (
      <div className={styles.page}>
        <Skeleton height={220} />
      </div>
    );
  }

  const msLeft = Math.max(0, Date.parse(data.expiresAt) - now);
  const minutesLeft = Math.ceil(msLeft / 60_000);
  const deadline = formatTime(data.expiresAt, data.timezone);
  const when = `${formatDate(data.startsAt, data.timezone)} в ${formatTime(data.startsAt, data.timezone)}`;
  const count = data.items.reduce((sum, item) => sum + item.qty, 0);

  const cancel = async () => {
    setConfirmCancel(false);
    setCancelError(null);
    try {
      await api.cancelOrder(data.id);
    } catch (error) {
      setCancelError(
        error instanceof ApiError && error.code === 'payment_uncertain'
          ? 'Банк ещё не ответил — отменить бронь пока нельзя.'
          : 'Не получилось отменить бронь. Проверьте интернет и попробуйте ещё раз.',
      );
      return;
    }
    tg.closingConfirmation(false);
    await tg.storage.set(ACTIVE_ORDER_KEY, '');
    await queryClient.invalidateQueries();
    navigate('/', { replace: true });
  };

  return (
    <main className={styles.page}>
      {view === 'waiting' ? (
        <Status icon={Hourglass} tone="accent" title="Бронь ждёт оплаты">
          <p className={styles.timerLine}>
            Места за вами ещё{' '}
            <span role="timer" className={`t-price ${styles.timer}`}>
              {formatLeft(msLeft)}
            </span>
          </p>
          <p className={styles.hint}>до {deadline}. Пока идёт таймер, места держим за вами.</p>
          <span className="sr-only" aria-live="polite">
            {ANNOUNCE_AT_MINUTES.has(minutesLeft) ? `Осталось ${minutesLeft} ${plural(minutesLeft, ['минута', 'минуты', 'минут'])}` : ''}
          </span>
        </Status>
      ) : null}
      {view === 'bank' ? (
        <Status icon={Landmark} tone="accent" title="Ждём подтверждения банка">
          <p className={styles.text}>Обычно хватает минуты. Повторно платить не нужно.</p>
        </Status>
      ) : null}
      {view === 'bankSlow' ? (
        <Status icon={Landmark} tone="muted" title="Банк отвечает дольше обычного">
          <p className={styles.text}>Если оплата прошла, билет придёт сообщением в бот. Страницу можно закрыть.</p>
        </Status>
      ) : null}
      {view === 'paid' ? (
        <Status icon={CircleCheck} tone="success" title="Билеты у вас">
          <p className={styles.text}>Ждём в {when}. Копия ушла в бот.</p>
        </Status>
      ) : null}
      {view === 'failed' ? (
        <Status icon={TriangleAlert} tone="error" title="Оплата не прошла">
          <p className={styles.text}>
            Деньги не списаны. Бронь ещё держим — {minutesLeft} {plural(minutesLeft, ['минуту', 'минуты', 'минут'])}.
          </p>
        </Status>
      ) : null}
      {view === 'expired' ? (
        <Status icon={TimerOff} tone="muted" title="Бронь закончилась">
          <p className={styles.text}>Десять минут прошли, места вернулись в продажу.</p>
        </Status>
      ) : null}
      {view === 'cancelled' ? (
        <Status icon={TimerOff} tone="muted" title="Бронь отменена">
          <p className={styles.text}>Места вернулись в продажу.</p>
        </Status>
      ) : null}
      {view === 'late' ? (
        <Status icon={Landmark} tone="muted" title="Проверяем оплату">
          <p className={styles.text}>Оплата дошла после окончания брони. Администратор проверит и напишет вам сегодня.</p>
        </Status>
      ) : null}

      <section className={styles.summary} aria-label="Заказ">
        <div className={styles.summaryTitle}>{data.eventTitle}</div>
        <div className={styles.summaryMeta}>
          {formatDate(data.startsAt, data.timezone)} · {formatTime(data.startsAt, data.timezone)}
        </div>
        <div className={styles.summaryRow}>
          <span>{ticketsLabel(count)}</span>
          <span className="t-price">{formatPrice(data.totalKopecks)}</span>
        </div>
      </section>

      {view === 'waiting' || view === 'failed' ? (
        <Button variant="link" onClick={() => setConfirmCancel(true)}>
          Отменить бронь
        </Button>
      ) : null}

      {cancelError ? (
        <p className={styles.error} role="alert">
          {cancelError}
        </p>
      ) : null}

      {confirmCancel ? (
        <Dialog
          title="Отменить бронь?"
          text="Места вернутся в продажу."
          confirmLabel="Отменить"
          cancelLabel="Оставить"
          onConfirm={() => void cancel()}
          onCancel={() => setConfirmCancel(false)}
        />
      ) : null}
    </main>
  );
}

function Status({
  icon: Icon,
  tone,
  title,
  children,
}: {
  icon: LucideIcon;
  tone: 'accent' | 'success' | 'error' | 'muted';
  title: string;
  children: ReactNode;
}) {
  return (
    <section className={styles.status}>
      <span className={`${styles.badge} ${styles[tone]}`}>
        <Icon size={28} strokeWidth={1.75} aria-hidden="true" />
      </span>
      <h1 className={`t-h1 ${styles.title}`}>{title}</h1>
      {children}
    </section>
  );
}
