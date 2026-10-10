import { ChevronLeft, ChevronRight, MapPin, Send } from 'lucide-react';
import { useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useApi } from '../api/ApiProvider';
import type { Ticket } from '../api/types';
import { formatDateTime } from '../lib/format';
import { useBackButton, useTg } from '../telegram/hooks';
import { STATUS_LABEL, useTickets } from '../tickets/useTickets';
import { Button } from '../ui/Button';
import { ErrorState } from '../ui/ErrorState';
import { ICON_STROKE } from '../ui/icons';
import { Pill } from '../ui/Pill';
import { Qr } from '../ui/Qr';
import { Skeleton } from '../ui/Skeleton';
import styles from './TicketScreen.module.css';

const SWIPE_PX = 50;

const INACTIVE_TEXT: Partial<Record<Ticket['status'], string>> = {
  used: 'По этому билету уже прошли.',
  returned: 'Деньги за билет вернули.',
  transferred: 'Билет передан другу.',
  event_cancelled: 'Вечер отменён. Деньги вернём полностью, напишем в боте.',
};

export function TicketScreen() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const api = useApi();
  const tg = useTg();
  const { tickets, fromCache, isError, refetch } = useTickets();
  const [shareError, setShareError] = useState(false);
  const swipeStart = useRef<number | null>(null);

  useBackButton(() => navigate('/tickets'));

  if (isError) {
    return (
      <ErrorState
        title="Нет связи"
        text="Проверьте интернет. Оплаченные билеты никуда не денутся."
        actionLabel="Повторить"
        onAction={refetch}
      />
    );
  }
  const ticket = tickets?.find((t) => t.id === id);
  if (!tickets) {
    return (
      <div className={styles.page}>
        <Skeleton height={320} />
      </div>
    );
  }
  if (!ticket) {
    return (
      <ErrorState
        title="Билет не найден"
        text="Возможно, его передали или вернули. Загляните в список билетов."
        actionLabel="К билетам"
        onAction={() => navigate('/tickets', { replace: true })}
      />
    );
  }

  const siblings = tickets.filter((t) => t.eventId === ticket.eventId).sort((a, b) => a.position - b.position);
  const index = siblings.findIndex((t) => t.id === ticket.id);
  const go = (step: number) => {
    const next = siblings[index + step];
    if (next) navigate(`/tickets/${next.id}`, { replace: true });
  };
  const valid = ticket.status === 'valid' && ticket.qrToken !== null;

  const share = async () => {
    setShareError(false);
    try {
      const { shareUrl } = await api.shareTicket(ticket.id);
      const text = `Билет на «${ticket.eventTitle}»`;
      tg.openTelegramLink(
        `https://t.me/share/url?url=${encodeURIComponent(shareUrl)}&text=${encodeURIComponent(text)}`,
      );
    } catch {
      setShareError(true);
    }
  };

  return (
    <main
      className={styles.page}
      onPointerDown={(e) => (swipeStart.current = e.clientX)}
      onPointerUp={(e) => {
        if (swipeStart.current === null) return;
        const dx = e.clientX - swipeStart.current;
        swipeStart.current = null;
        if (Math.abs(dx) > SWIPE_PX) go(dx < 0 ? 1 : -1);
      }}
    >
      <header className={styles.header}>
        <h1 className={`t-h2 ${styles.title}`}>{ticket.eventTitle}</h1>
        <p className={styles.meta}>
          {formatDateTime(ticket.startsAt, ticket.timezone)} · {ticket.typeName}
        </p>
        <Pill tone={valid ? 'success' : 'muted'}>{STATUS_LABEL[ticket.status]}</Pill>
      </header>

      <section className={styles.card}>
        {valid ? (
          <>
            <Qr value={ticket.qrToken!} size={260} />
            <p className={styles.count}>
              Билет {ticket.position} из {ticket.ofCount}
            </p>
            <p className={styles.hint}>Покажите QR на входе</p>
            <p className={styles.code}>Номер {ticket.shortCode} — если QR не читается</p>
          </>
        ) : (
          <p className={styles.inactive}>{INACTIVE_TEXT[ticket.status] ?? STATUS_LABEL[ticket.status]}</p>
        )}
        {siblings.length > 1 ? (
          <div className={styles.pager}>
            <button
              type="button"
              className={styles.pageButton}
              aria-label="Предыдущий билет"
              disabled={index <= 0}
              onClick={() => go(-1)}
            >
              <ChevronLeft size={20} strokeWidth={ICON_STROKE} aria-hidden="true" />
            </button>
            <span className={styles.dots} aria-hidden="true">
              {siblings.map((s) => (
                <span key={s.id} className={`${styles.dot} ${s.id === ticket.id ? styles.dotActive : ''}`} />
              ))}
            </span>
            <button
              type="button"
              className={styles.pageButton}
              aria-label="Следующий билет"
              disabled={index >= siblings.length - 1}
              onClick={() => go(1)}
            >
              <ChevronRight size={20} strokeWidth={ICON_STROKE} aria-hidden="true" />
            </button>
          </div>
        ) : null}
      </section>

      {fromCache ? <p className={styles.cached}>Билет сохранён на телефоне</p> : null}

      <div className={styles.actions}>
        {ticket.mapUrl ? (
          <Button variant="outline" wide onClick={() => tg.openLink(ticket.mapUrl!)}>
            <MapPin size={20} strokeWidth={ICON_STROKE} aria-hidden="true" />
            На карте
          </Button>
        ) : null}
        {valid && !fromCache ? (
          <Button variant="outline" wide onClick={() => void share()}>
            <Send size={20} strokeWidth={ICON_STROKE} aria-hidden="true" />
            Отправить другу
          </Button>
        ) : null}
        {shareError ? <p className={styles.error}>Не получилось создать ссылку. Попробуйте ещё раз.</p> : null}
        {ticket.address ? <p className={styles.address}>{ticket.address}</p> : null}
      </div>
    </main>
  );
}
