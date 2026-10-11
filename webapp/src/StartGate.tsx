import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useApi } from './api/ApiProvider';
import type { Me } from './api/types';
import { ACTIVE_ORDER_KEY, resolveStart } from './start';
import { useTg } from './telegram/hooks';
import { Skeleton } from './ui/Skeleton';

type Phase = 'loading' | 'ready';

/** Asks the server who the guest is, then opens the right screen. */
export function StartGate({ children }: { children: ReactNode }) {
  const api = useApi();
  const tg = useTg();
  const navigate = useNavigate();
  const location = useLocation();
  const [phase, setPhase] = useState<Phase>('loading');
  const started = useRef(false);

  const open = useCallback(
    async (who: Me) => {
      let path = resolveStart(tg.startParam, who);
      if (!who.activeOrder) {
        const stored = await tg.storage.get(ACTIVE_ORDER_KEY);
        if (stored) {
          try {
            const order = await api.order(stored);
            if (order.status === 'pending' || order.status === 'paid') path = `/order/${order.id}`;
            else await tg.storage.set(ACTIVE_ORDER_KEY, '');
          } catch {
            await tg.storage.set(ACTIVE_ORDER_KEY, '');
          }
        }
      }
      // Nothing to open on purpose: stay where the app was (re)loaded.
      if (path === '/' && location.pathname !== '/') {
        setPhase('ready');
        return;
      }
      // A deep link sits on top of the afisha, so «назад» leads there.
      navigate('/', { replace: true });
      if (path !== '/') navigate(path);
      setPhase('ready');
    },
    [api, tg, navigate, location.pathname],
  );

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    api
      .me()
      .then(open)
      // Offline or server trouble: each screen shows its own error with a retry.
      .catch(() => setPhase('ready'));
  }, [api, open]);

  if (phase === 'loading') {
    return (
      <div style={{ padding: 16 }}>
        <Skeleton height={200} />
      </div>
    );
  }
  return <>{children}</>;
}
