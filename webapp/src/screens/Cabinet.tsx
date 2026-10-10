import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { MessageCircle, RotateCcw } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApi } from '../api/ApiProvider';
import type { Ticket } from '../api/types';
import { formatDate, plural } from '../lib/format';
import { useTg } from '../telegram/hooks';
import { STATUS_LABEL, useTickets } from '../tickets/useTickets';
import { Dialog } from '../ui/Dialog';
import { ListRow } from '../ui/ListRow';
import { PaperTicket } from '../ui/PaperTicket';
import { Skeleton } from '../ui/Skeleton';
import { TicketFan } from '../ui/TicketFan';
import { Toggle } from '../ui/Toggle';
import styles from './Cabinet.module.css';

/** The club's bot; «Написать организатору» opens the chat with it. */
export const BOT_URL = 'https://t.me/povod_club_bot';

const byStart = (a: Ticket, b: Ticket) => Date.parse(a.startsAt) - Date.parse(b.startsAt) || a.position - b.position;

/** Cabinet: profile, my tickets in a fan, torn souvenirs, support and privacy (spec v2 §5). No glow here. */
export function Cabinet() {
  const api = useApi();
  const tg = useTg();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { tickets, isPending } = useTickets();
  const me = useQuery({ queryKey: ['me'], queryFn: () => api.me() });
  const privacy = useMutation({
    mutationFn: (value: boolean) => api.setShowInAttendees(value),
    onSuccess: (next) => queryClient.setQueryData(['me'], next),
  });
  const [index, setIndex] = useState(0);
  const [howToReturn, setHowToReturn] = useState(false);

  const now = Date.now();
  const all = tickets ?? [];
  const active = all.filter((t) => t.status === 'valid' && Date.parse(t.startsAt) > now - 6 * 60 * 60 * 1000).sort(byStart);
  const rest = all.filter((t) => !active.includes(t)).sort((a, b) => byStart(b, a));
  // One souvenir per evening, however many tickets the guest had for it.
  const souvenirs = rest.filter((t, i) => t.status === 'used' && rest.findIndex((o) => o.status === 'used' && o.eventId === t.eventId) === i);
  const evenings = souvenirs.length;
  const name = tg.user?.firstName ?? 'Гость';
  const showInAttendees = privacy.isPending ? Boolean(privacy.variables) : (me.data?.showInAttendees ?? false);

  return (
    <main className={styles.page}>
      <header className={styles.profile}>
        {tg.user?.photoUrl ? (
          <img className={styles.avatar} src={tg.user.photoUrl} alt="" />
        ) : (
          <span className={styles.avatar} aria-hidden="true">
            {name.charAt(0).toUpperCase()}
          </span>
        )}
        <h1 className={`t-h1 ${styles.name}`}>{name}</h1>
        {evenings > 0 ? (
          <p className={styles.evenings}>
            {evenings} {plural(evenings, ['вечер', 'вечера', 'вечеров'])} с нами
          </p>
        ) : null}
      </header>

      <section className={styles.section} aria-labelledby="my-tickets">
        <h2 id="my-tickets" className={`t-h2 ${styles.heading}`}>
          Мои билеты
        </h2>
        {isPending && !tickets ? (
          <Skeleton height={420} />
        ) : active.length ? (
          <div className={styles.fan}>
            <TicketFan
              tickets={active}
              index={index}
              onIndex={setIndex}
              onOpen={(t) => navigate(`/tickets/${t.id}`)}
              render={(t) => <PaperTicket ticket={t} guestName={tg.user?.firstName ?? null} />}
            />
          </div>
        ) : (
          <div className={styles.empty}>
            <p className={`t-h3 ${styles.emptyTitle}`}>Билетов пока нет</p>
            <p className={styles.emptyText}>Выбери вечер на главной — билет появится здесь.</p>
          </div>
        )}
        {rest.length ? (
          <details className={styles.past}>
            <summary className={styles.pastSummary}>Прошедшие · {rest.length}</summary>
            <ul className={styles.pastList}>
              {rest.map((t) => (
                <li key={t.id}>
                  <button type="button" className={styles.pastRow} onClick={() => navigate(`/tickets/${t.id}`)}>
                    <span className={styles.pastTitle}>{t.eventTitle}</span>
                    <span className={styles.pastMeta}>
                      {formatDate(t.startsAt, t.timezone)} · {STATUS_LABEL[t.status]}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </section>

      {souvenirs.length ? (
        <section className={styles.section} aria-labelledby="my-evenings">
          <h2 id="my-evenings" className={`t-h2 ${styles.heading}`}>
            Мои вечера
          </h2>
          <div className={styles.souvenirs}>
            {souvenirs.map((t) => (
              <div key={t.id} className={styles.souvenir}>
                <PaperTicket ticket={t} guestName={tg.user?.firstName ?? null} torn />
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className={styles.section} aria-labelledby="support">
        <h2 id="support" className={`t-h2 ${styles.heading}`}>
          Поддержка
        </h2>
        <div className={styles.rows}>
          <ListRow icon={MessageCircle} label="Написать организатору" onClick={() => tg.openTelegramLink(BOT_URL)} />
          <ListRow icon={RotateCcw} label="Как вернуть билет" onClick={() => setHowToReturn(true)} />
        </div>
      </section>

      <section className={styles.section} aria-labelledby="privacy">
        <h2 id="privacy" className={`t-h2 ${styles.heading}`}>
          Приватность
        </h2>
        <ListRow
          label="Показывать меня в списке гостей"
          trailing={
            <Toggle
              label="Показывать меня в списке гостей"
              checked={showInAttendees}
              disabled={!me.data || privacy.isPending}
              onChange={(next) => privacy.mutate(next)}
            />
          }
        />
      </section>

      {howToReturn ? (
        <Dialog
          title="Как вернуть билет"
          text="Полный возврат — если до вечера больше 3 дней. Напиши организатору в бот, и мы всё оформим."
          confirmLabel="Написать"
          cancelLabel="Понятно"
          onConfirm={() => {
            setHowToReturn(false);
            tg.openTelegramLink(BOT_URL);
          }}
          onCancel={() => setHowToReturn(false)}
        />
      ) : null}
    </main>
  );
}
