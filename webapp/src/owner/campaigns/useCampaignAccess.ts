import { useCampaignApi } from '../../api/campaigns/CampaignApiProvider';
import { useOwnerPermissions } from '../useOwnerAccess';

/** True for a role with `manage_campaigns`, and only where the broadcasts API is available. */
export function useCampaignAccess(): boolean {
  const api = useCampaignApi();
  const permissions = useOwnerPermissions();
  return api !== null && permissions.includes('manage_campaigns');
}
