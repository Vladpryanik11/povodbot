import { useQuery } from '@tanstack/react-query';
import { useOwnerApi } from '../api/owner/OwnerApiProvider';

/** The signed-in role's permissions; any failure of the check means none. */
export function useOwnerPermissions(): string[] {
  const api = useOwnerApi();
  const me = useQuery({ queryKey: ['owner', 'me'], queryFn: () => api.me(), retry: false, staleTime: Infinity });
  return me.data?.permissions ?? [];
}

/** True only for a role with `manage_events`; any failure of the check keeps owner mode hidden. */
export function useOwnerAccess(): boolean {
  return useOwnerPermissions().includes('manage_events');
}
