import { Navigate, Route, Routes } from 'react-router-dom';
import { useCampaignApi } from '../../../api/campaigns/CampaignApiProvider';
import { CampaignList } from './CampaignList';
import { CampaignScreen } from './CampaignScreen';
import { CampaignStart } from './CampaignStart';
import { TemplateEditor } from './TemplateEditor';
import { Templates } from './Templates';

/** /owner/campaigns/*; where the broadcasts API is not available yet, owner mode opens on evenings. */
export function CampaignRoutes() {
  if (useCampaignApi() === null) return <Navigate to="/owner" replace />;
  return (
    <Routes>
      <Route index element={<CampaignList />} />
      <Route path="start" element={<CampaignStart />} />
      <Route path="templates" element={<Templates />} />
      <Route path="templates/:id" element={<TemplateEditor />} />
      <Route path=":id" element={<CampaignScreen />} />
    </Routes>
  );
}
