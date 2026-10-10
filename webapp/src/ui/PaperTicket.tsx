import { useState } from 'react';
import type { Ticket, TicketStatus } from '../api/types';
import { formatDate, formatDayMonth, formatTime } from '../lib/format';
import { posterColor } from '../lib/posterColor';
import { usablePhoto } from './PosterImage';
import { Qr } from './Qr';
import styles from './PaperTicket.module.css';

/** Statuses that grey the whole ticket out; the stub stays, without the QR. */
const INACTIVE: Partial<Record<TicketStatus, string>> = {
  returned: 'Возвращён',
  transferred: 'Передан',
  event_cancelled: 'Вечер отменён',
};

interface Props {
  ticket: Ticket;
  /** First name from Telegram; null outside Telegram. */
  guestName: string | null;
  /** Used tickets only: false on the first show, so the stub is still there to tear off (spec v2 §7). */
  torn?: boolean;
}

/** Paper ticket: poster, 2×2 data, perforation with side cut-outs, stub with the QR (spec v2 §6). */
export function PaperTicket({ ticket, guestName, torn = true }: Props) {
  const [stubGone, setStubGone] = useState(false);
  const used = ticket.status === 'used';
  const inactive = INACTIVE[ticket.status];
  const valid = ticket.status === 'valid' && ticket.qrToken !== null;
  const tearing = used && !torn && !stubGone;
  const stub = !used || tearing;
  const badge = used ? `Было · ${formatDayMonth(ticket.startsAt, ticket.timezone)}` : inactive;

  return (
    <article className={styles.ticket} data-inactive={inactive ? '' : undefined} aria-label={`Билет на «${ticket.eventTitle}»`}>
      <div className={`${styles.main} ${stub ? styles.cut : ''}`}>
        <div className={styles.poster}>
          {usablePhoto(ticket.poster) ? (
            <img className={styles.photo} src={ticket.poster.url} alt="" aria-hidden="true" />
          ) : (
            <div className={styles.photo} style={{ backgroundColor: posterColor(ticket.eventTitle) }} aria-hidden="true" />
          )}
          <div className={styles.scrim} />
          {badge ? <span className={styles.badge}>{badge}</span> : null}
          <div className={styles.caption}>
            <h2 className={`t-h3 ${styles.title}`}>{ticket.eventTitle}</h2>
            <p className={styles.date}>{formatDate(ticket.startsAt, ticket.timezone)}</p>
          </div>
        </div>
        <ul className={styles.grid} aria-label="Данные билета">
          <Cell label="Гость" value={guestName ?? '—'} />
          <Cell label="Дата" value={formatDate(ticket.startsAt, ticket.timezone)} />
          <Cell label="Вход" value={formatTime(ticket.startsAt, ticket.timezone)} />
          <Cell label="Билет" value={ticket.typeName} />
        </ul>
      </div>
      {stub ? (
        <div className={styles.stub} data-testid="stub" data-tearing={tearing ? '' : undefined} onAnimationEnd={() => setStubGone(true)}>
          {valid ? <Qr value={ticket.qrToken!} size={240} /> : null}
          <p className={styles.code}>Номер {ticket.shortCode}</p>
          <p className={styles.count}>
            Билет {ticket.position} из {ticket.ofCount}
          </p>
        </div>
      ) : null}
    </article>
  );
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <li className={styles.cell}>
      <span className={styles.label}>{label}</span>
      <span className={styles.value}>{value}</span>
    </li>
  );
}
