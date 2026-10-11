import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useApi, useMockApi } from '../api/ApiProvider';
import { formatPrice } from '../lib/format';
import { Button } from '../ui/Button';
import styles from './MockPay.module.css';

/** Stage A stand-in for the T‑Bank page: the guest decides, the scenario may override (see MockApi). */
export function MockPay() {
  const { id = '' } = useParams();
  const api = useApi();
  const mock = useMockApi();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const order = useQuery({ queryKey: ['order', id], queryFn: () => api.order(id) });
  const [busy, setBusy] = useState(false);

  const decide = async (outcome: 'paid' | 'failed') => {
    if (!mock || busy) return;
    setBusy(true);
    await mock.completePayment(id, outcome);
    await queryClient.invalidateQueries();
    navigate(`/order/${id}`, { replace: true });
  };

  return (
    // The bank page is always light, whatever the Telegram theme.
    <main className={styles.page} data-theme="light">
      <p className={styles.badge}>Тестовая оплата</p>
      <h1 className={styles.title}>Оплата заказа</h1>
      <p className={styles.amount}>{order.data ? formatPrice(order.data.totalKopecks) : '…'}</p>
      <p className={styles.note}>Это имитация страницы банка. Настоящая оплата подключается на следующем этапе.</p>
      <div className={styles.actions}>
        <Button wide loading={busy} onClick={() => void decide('paid')} disabled={!mock}>
          Оплатить
        </Button>
        <Button wide variant="secondary" onClick={() => void decide('failed')} disabled={!mock || busy}>
          Отказаться
        </Button>
      </div>
    </main>
  );
}
