import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { ApiProvider } from '../api/ApiProvider';
import type { CampaignApi } from '../api/campaigns/CampaignApi';
import { CampaignApiProvider } from '../api/campaigns/CampaignApiProvider';
import { MockCampaignApi } from '../api/campaigns/MockCampaignApi';
import type { AppApi } from '../api/AppApi';
import { MockApi } from '../api/mock/MockApi';
import { MockOwnerApi } from '../api/owner/MockOwnerApi';
import type { OwnerApi } from '../api/owner/OwnerApi';
import { OwnerApiProvider } from '../api/owner/OwnerApiProvider';
import { TgProvider } from '../telegram/hooks';
import { createTg, type TgFacade } from '../telegram/tg';
import { BottomBar } from '../ui/BottomBar';

export const T0 = Date.parse('2026-10-10T09:00:00Z');

export function Where() {
  return <output data-testid="where">{useLocation().pathname}</output>;
}

interface Options {
  api?: AppApi;
  ownerApi?: OwnerApi;
  /** null: broadcasts unavailable (inside Telegram until stage 3). */
  campaignApi?: CampaignApi | null;
  tg?: TgFacade;
  /** Initial URL, e.g. '/events/e-film'. */
  at?: string;
  /** Route pattern the screen is mounted on, e.g. '/events/:id'. */
  path?: string;
}

/** Renders a screen with the same providers as the app, at a route, plus the page bottom bar. */
export function renderScreen(screen: ReactElement, options: Options = {}) {
  const api = options.api ?? new MockApi({ latencyMs: 0, now: () => T0 });
  const ownerApi = options.ownerApi ?? new MockOwnerApi({ latencyMs: 0, now: () => T0 });
  const campaignApi =
    options.campaignApi === undefined
      ? new MockCampaignApi({ latencyMs: 0, now: () => T0 })
      : options.campaignApi;
  const tg = options.tg ?? createTg();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const at = options.at ?? '/';
  const view = render(
    <QueryClientProvider client={client}>
      <TgProvider value={tg}>
        <ApiProvider api={api}>
          <OwnerApiProvider api={ownerApi}>
            <CampaignApiProvider api={campaignApi}>
              <MemoryRouter initialEntries={[at]}>
                <Routes>
                  <Route path={options.path ?? at} element={screen} />
                  <Route path="*" element={null} />
                </Routes>
                <Where />
                <BottomBar />
              </MemoryRouter>
            </CampaignApiProvider>
          </OwnerApiProvider>
        </ApiProvider>
      </TgProvider>
    </QueryClientProvider>,
  );
  return { ...view, api, ownerApi, campaignApi, tg, client };
}
