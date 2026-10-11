import { useQuery } from '@tanstack/react-query';
import { useOwnerApi } from '../api/owner/OwnerApiProvider';

/** True only for a role with `manage_events`; any failure of the check keeps owner mode hidden. */
export function useOwnerAccess(): boolean {
  const api = useOwnerApi();
  const me = useQuery({ queryKey: ['owner', 'me'], queryFn: () => api.me(), retry: false, staleTime: Infinity });
  return me.data?.permissions.includes('manage_events') ?? false;
}
