import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';
import { useTg } from '../telegram/hooks';

const KEY = 'fav';
const LIMIT = 100;
const QUERY_KEY = ['favorites'] as const;

/** Whatever CloudStorage holds becomes a clean list: strings only, no duplicates, the last hundred. */
export function parseFavorites(raw: string | null): string[] {
  if (!raw) return [];
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(value)) return [];
  const ids = [...new Set(value.filter((v): v is string => typeof v === 'string'))];
  return ids.slice(-LIMIT);
}

/** Saved events, shared by every heart on screen through the query cache; writes are optimistic. */
export function useFavorites(): { ids: string[]; ready: boolean; has(id: string): boolean; toggle(id: string): void } {
  const tg = useTg();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: QUERY_KEY,
    queryFn: async () => parseFavorites(await tg.storage.get(KEY)),
    staleTime: Infinity,
  });
  const ids = query.data ?? [];

  const toggle = useCallback(
    (id: string) => {
      const current = client.getQueryData<string[]>(QUERY_KEY) ?? [];
      const next = current.includes(id) ? current.filter((x) => x !== id) : [...current, id].slice(-LIMIT);
      client.setQueryData(QUERY_KEY, next);
      void tg.storage.set(KEY, JSON.stringify(next));
    },
    [client, tg],
  );

  return { ids, ready: query.isSuccess, has: (id) => ids.includes(id), toggle };
}
