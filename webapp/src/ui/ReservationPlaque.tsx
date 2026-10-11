import { Timer } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Order } from '../api/types';
import { useCountdown } from '../checkout/useCountdown';
import { ICON_STROKE } from './icons';
import styles from './ReservationPlaque.module.css';

/** Glass plaque above the tab bar while a reservation waits for payment (spec v2 §5, item 6). */
export function ReservationPlaque({ order }: { order: Order }) {
  const { left, expired } = useCountdown(order.expiresAt);
  // Past the deadline the hold is gone; a plaque frozen on 00:00 would promise a seat that is not there.
  if (expired) return null;
  return (
    <Link to={`/order/${order.id}`} className={`glass ${styles.plaque}`}>
      <Timer size={20} strokeWidth={ICON_STROKE} aria-hidden="true" />
      <span>Бронь ждёт оплаты · {left}</span>
    </Link>
  );
}
