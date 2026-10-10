import { useEffect, useState } from 'react';

export function formatLeft(ms: number): string {
  const total = Math.max(0, Math.ceil(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

/** Ticks once a second until `expiresAt`; `left` is MM:SS and never goes below 00:00. */
export function useCountdown(expiresAt: string, now: () => number = Date.now) {
  const deadline = Date.parse(expiresAt);
  const [msLeft, setMsLeft] = useState(() => deadline - now());

  useEffect(() => {
    setMsLeft(deadline - now());
    const timer = setInterval(() => setMsLeft(deadline - now()), 1000);
    return () => clearInterval(timer);
  }, [deadline, now]);

  return { left: formatLeft(msLeft), expired: msLeft <= 0, msLeft: Math.max(0, msLeft) };
}
