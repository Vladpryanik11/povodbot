import { createContext, useContext, type ReactNode } from 'react';
import { scenarioFromUrl } from '../mock/MockApi';
import { ownerRoleFromUrl } from '../owner/MockOwnerApi';
import type { CampaignApi } from './CampaignApi';
import { MockCampaignApi } from './MockCampaignApi';

/** null: broadcasts are not available here, and the screens hide the tab. */
const Context = createContext<CampaignApi | null | undefined>(undefined);

let fallback: CampaignApi | null | undefined;

/** Inside Telegram there is no HTTP client yet (stage 3), so the tab stays hidden; in a plain browser use the mock. */
function getFallback(): CampaignApi | null {
  if (fallback === undefined) {
    fallback = window.Telegram?.WebApp?.initData
      ? null
      : new MockCampaignApi({ role: ownerRoleFromUrl(), offline: scenarioFromUrl() === 'offline' });
  }
  return fallback;
}

export function CampaignApiProvider({ api, children }: { api?: CampaignApi | null; children: ReactNode }) {
  return <Context.Provider value={api === undefined ? getFallback() : api}>{children}</Context.Provider>;
}

export function useCampaignApi(): CampaignApi | null {
  const api = useContext(Context);
  return api === undefined ? getFallback() : api;
}

/** For screens behind CampaignRoutes, which only mount when the API exists. */
export function useRequiredCampaignApi(): CampaignApi {
  const api = useCampaignApi();
  if (!api) throw new Error('Campaign screens need a CampaignApi');
  return api;
}
