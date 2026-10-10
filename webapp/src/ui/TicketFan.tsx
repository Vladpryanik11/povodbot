import { useRef, useState, type CSSProperties, type ReactNode } from 'react';
import type { Ticket } from '../api/types';
import styles from './TicketFan.module.css';

const SWIPE_PX = 40;
/** Movement under this is still a tap, not a drag. */
const TAP_SLOP_PX = 6;

interface Props {
  tickets: Ticket[];
  index: number;
  onIndex(i: number): void;
  /** Tap on the ticket in front. */
  onOpen?(ticket: Ticket): void;
  render(ticket: Ticket): ReactNode;
}

const clamp = (i: number, n: number) => Math.max(0, Math.min(n - 1, i));

/** Fan of tickets: the current one in front, neighbours peeking at the sides, turned ±6°; swipe, keys or dots (spec v2 §6). */
export function TicketFan({ tickets, index, onIndex, onOpen, render }: Props) {
  const n = tickets.length;
  const current = clamp(index, n);
  const [drag, setDrag] = useState(0);
  const start = useRef<number | null>(null);
  const moved = useRef(false);

  const go = (i: number) => {
    const next = clamp(i, n);
    if (next !== current) onIndex(next);
  };

  const release = () => {
    if (start.current === null) return;
    start.current = null;
    if (Math.abs(drag) > SWIPE_PX) go(current + (drag < 0 ? 1 : -1));
    setDrag(0);
  };

  return (
    <div
      className={styles.fan}
      role="region"
      aria-label="Билеты"
      aria-roledescription="карусель"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'ArrowRight') go(current + 1);
        else if (e.key === 'ArrowLeft') go(current - 1);
      }}
      onPointerDown={(e) => {
        start.current = e.clientX;
        moved.current = false;
      }}
      onPointerMove={(e) => {
        if (start.current === null) return;
        const dx = e.clientX - start.current;
        if (Math.abs(dx) > TAP_SLOP_PX) moved.current = true;
        setDrag(dx);
      }}
      onPointerUp={release}
      onPointerCancel={release}
      onPointerLeave={release}
    >
      <div className={styles.track} data-dragging={drag !== 0 || undefined} style={{ '--drag': `${drag}px` } as CSSProperties}>
        {tickets.map((ticket, i) => {
          const offset = i - current;
          return (
            <div
              key={ticket.id}
              className={styles.card}
              data-current={offset === 0 || undefined}
              data-side={offset === 0 ? undefined : offset < 0 ? 'prev' : 'next'}
              data-far={Math.abs(offset) > 1 || undefined}
              aria-hidden={offset === 0 ? undefined : true}
              onClick={() => {
                if (moved.current) return;
                if (offset === 0) onOpen?.(ticket);
                else go(i);
              }}
            >
              {render(ticket)}
            </div>
          );
        })}
      </div>
      {n > 1 ? (
        <div className={styles.dots} role="tablist" aria-label="Билеты в заказе">
          {tickets.map((ticket, i) => (
            <button
              key={ticket.id}
              type="button"
              role="tab"
              aria-selected={i === current}
              aria-label={`Показать билет ${i + 1}`}
              className={styles.dot}
              onClick={() => go(i)}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
