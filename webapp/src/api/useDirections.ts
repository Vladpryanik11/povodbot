import { useQuery } from '@tanstack/react-query';
import { useApi } from './ApiProvider';
import type { Direction } from './types';

/** Directions rarely change; one cached query serves every card and the filter chips. */
export function useDirections(): Direction[] {
  const api = useApi();
  return useQuery({ queryKey: ['directions'], queryFn: () => api.directions(), staleTime: Infinity }).data ?? [];
}
