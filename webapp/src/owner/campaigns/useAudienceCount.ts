import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useRequiredCampaignApi } from '../../api/campaigns/CampaignApiProvider';
import type { AudienceFilter } from '../../api/campaigns/types';

const DEBOUNCE_MS = 300;

/** Counts the audience 300 ms after the last change; an answer for an older filter never shows. */
export function useAudienceCount(filter: AudienceFilter): { count: number | null; overLimit: number; pending: boolean } {
  const api = useRequiredCampaignApi();
  const key = JSON.stringify(filter);
  const [settled, setSettled] = useState(key);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(key), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [key]);
  const query = useQuery({
    queryKey: ['campaigns', 'audience', settled],
    queryFn: () => api.audienceCount(JSON.parse(settled) as AudienceFilter),
    placeholderData: keepPreviousData,
  });
  return {
    count: query.data?.count ?? null,
    overLimit: query.data?.overLimit ?? 0,
    pending: settled !== key || query.isFetching,
  };
}
