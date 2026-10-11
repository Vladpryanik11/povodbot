import { MapPin, Send } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useApi } from '../api/ApiProvider';
import type { Ticket } from '../api/types';
import { useBackButton, useTg } from '../telegram/hooks';
import { useTickets } from '../tickets/useTickets';
import { Button } from '../ui/Button';
import { ErrorState } from '../ui/ErrorState';
import { useGlow } from '../ui/Glow';
import { ICON_STROKE } from '../ui/icons';
import { PaperTicket } from '../ui/PaperTicket';
import { Skeleton } from '../ui/Skeleton';
import { TicketFan } from '../ui/TicketFan';
import { useEventColor } from '../ui/useEventColor';
import styles from './TicketScreen.module.css';

const INACTIVE_TEXT: Partial<Record<Ticket['status'], string>> = {
  used: 'По этому билету уже прошли.',
  returned: 'Деньги за билет вернули.',
  transferred: 'Билет передан другу.',
  event_cancelled: 'Вечер отменён. Деньги вернём полностью, напишем в боте.',
};

const tornKey = (id: string) => `torn:${id}`;

/** Paper tickets of one evening in a fan, on the glow of its poster (spec v2 §6). */
export function TicketScreen() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const api = useApi();
  const tg = useTg();
  const { tickets, fromCache, isError, refetch } = useTickets();
  const [shareError, setShareError] = useState(false);
  /** Used tickets: whether the stub was already torn off on an earlier visit. */
  const [seen, setSeen] = useState<Record<string, boolean>>({});
  const ticket = tickets?.find((t) => t.id === id);
  const color = useEventColor(ticket ? { title: ticket.eventTitle, accentColor: null, poster: ticket.poster } : null);
  useGlow(color);

  useBackButton(() => navigate('/me'));

  const usedId = ticket?.status === 'used' ? ticket.id : null;
  useEffect(() => {
    if (!usedId) return;
    let live = true;
    tg.storage.get(tornKey(usedId)).then(
      (flag) => {
        if (!live) return;
        setSeen((s) => (usedId in s ? s : { ...s, [usedId]: flag !== null }));
        if (flag === null) void tg.storage.set(tornKey(usedId), '1');
      },
      () => live && setSeen((s) => ({ ...s, [usedId]: true })),
    );
    return () => {
      live = false;
    };
  }, [usedId, tg]);

  if (isError) {
    return (
      <ErrorState
        title="Нет связи"
        text="Проверь интернет. Купленные билеты никуда не денутся."
        actionLabel="Повторить"
        onAction={refetch}
      />
    );
  }
  // A used ticket waits for its torn flag, so the stub doesn't flash in and out.
  if (!tickets || (usedId && !(usedId in seen))) {
    return (
      <div className={styles.page}>
        <Skeleton height={420} />
      </div>
    );
  }
  if (!ticket) {
    return (
      <ErrorState
        title="Билет не найден"
        text="Возможно, его передали или вернули. Загляни в кабинет."
        actionLabel="В кабинет"
        onAction={() => navigate('/me', { replace: true })}
      />
    );
  }

  const siblings = tickets.filter((t) => t.eventId === ticket.eventId).sort((a, b) => a.position - b.position);
  const index = siblings.findIndex((t) => t.id === ticket.id);
  const valid = ticket.status === 'valid' && ticket.qrToken !== null;
  const guestName = tg.user?.firstName ?? null;

  const share = async () => {
    setShareError(false);
    try {
      const { shareUrl } = await api.shareTicket(ticket.id);
      const text = `Билет на «${ticket.eventTitle}»`;
      tg.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(shareUrl)}&text=${encodeURIComponent(text)}`);
    } catch {
      setShareError(true);
    }
  };

  return (
    <main className={styles.page}>
      <TicketFan
        tickets={siblings}
        index={index}
        onIndex={(i) => navigate(`/tickets/${siblings[i].id}`, { replace: true })}
        render={(t) => <PaperTicket ticket={t} guestName={guestName} torn={seen[t.id] !== false} />}
      />

      {!valid && INACTIVE_TEXT[ticket.status] ? <p className={styles.inactive}>{INACTIVE_TEXT[ticket.status]}</p> : null}
      {fromCache ? <p className={styles.cached}>Билет сохранён на телефоне</p> : null}

      <div className={styles.actions}>
        {ticket.mapUrl ? (
          <Button variant="secondary" wide onClick={() => tg.openLink(ticket.mapUrl!)}>
            <MapPin size={20} strokeWidth={ICON_STROKE} aria-hidden="true" />
            Построить маршрут
          </Button>
        ) : null}
        {valid && !fromCache ? (
          <Button variant="secondary" wide onClick={() => void share()}>
            <Send size={20} strokeWidth={ICON_STROKE} aria-hidden="true" />
            Отправить другу
          </Button>
        ) : null}
        {shareError ? <p className={styles.error}>Не получилось создать ссылку. Попробуй ещё раз.</p> : null}
        {ticket.address ? <p className={styles.address}>{ticket.address}</p> : null}
      </div>
    </main>
  );
}
