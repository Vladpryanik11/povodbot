import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { ApiProvider } from '../api/ApiProvider';
import type { AppApi } from '../api/AppApi';
import { MockApi } from '../api/mock/MockApi';
import { TgProvider } from '../telegram/hooks';
import { createTg, type TgFacade } from '../telegram/tg';
import { BottomBar } from '../ui/BottomBar';

export const T0 = Date.parse('2026-10-10T09:00:00Z');

export function Where() {
  return <output data-testid="where">{useLocation().pathname}</output>;
}

interface Options {
  api?: AppApi;
  tg?: TgFacade;
  /** Initial URL, e.g. '/events/e-film'. */
  at?: string;
  /** Route pattern the screen is mounted on, e.g. '/events/:id'. */
  path?: string;
}

/** Renders a screen with the same providers as the app, at a route, plus the page bottom bar. */
export function renderScreen(screen: ReactElement, options: Options = {}) {
  const api = options.api ?? new MockApi({ latencyMs: 0, now: () => T0 });
  const tg = options.tg ?? createTg();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const at = options.at ?? '/';
  const view = render(
    <QueryClientProvider client={client}>
      <TgProvider value={tg}>
        <ApiProvider api={api}>
          <MemoryRouter initialEntries={[at]}>
            <Routes>
              <Route path={options.path ?? at} element={screen} />
              <Route path="*" element={null} />
            </Routes>
            <Where />
            <BottomBar />
          </MemoryRouter>
        </ApiProvider>
      </TgProvider>
    </QueryClientProvider>,
  );
  return { ...view, api, tg, client };
}
