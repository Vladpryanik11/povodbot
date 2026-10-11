import { Navigate, Route, Routes } from 'react-router-dom';
import { useCampaignApi } from '../../../api/campaigns/CampaignApiProvider';
import { CampaignList } from './CampaignList';

/** /owner/campaigns/*; where the broadcasts API is not available yet, owner mode opens on evenings. */
export function CampaignRoutes() {
  if (useCampaignApi() === null) return <Navigate to="/owner" replace />;
  return (
    <Routes>
      <Route index element={<CampaignList />} />
    </Routes>
  );
}
