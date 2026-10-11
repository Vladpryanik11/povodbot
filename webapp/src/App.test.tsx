import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { ApiProvider } from './api/ApiProvider';
import { MockApi } from './api/mock/MockApi';
import { App } from './App';
import { TgProvider } from './telegram/hooks';
import { createTg, type TgFacade } from './telegram/tg';

const T0 = Date.parse('2026-10-10T09:00:00Z');

function Where() {
  return <output data-testid="where">{useLocation().pathname}</output>;
}

function renderApp(api: MockApi, tg: TgFacade, at = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <TgProvider value={tg}>
        <ApiProvider api={api}>
          <MemoryRouter initialEntries={[at]}>
            <App />
            <Where />
          </MemoryRouter>
        </ApiProvider>
      </TgProvider>
    </QueryClientProvider>,
  );
}

function tgWithStart(startParam: string | null): TgFacade {
  const tg = createTg();
  return Object.assign(Object.create(Object.getPrototypeOf(tg)), tg, { startParam });
}

describe('App start', () => {
  it('opens the event from a deep link and the afisha without one', async () => {
    const first = renderApp(new MockApi({ latencyMs: 0, now: () => T0 }), tgWithStart('event_e-film'));
    expect(await screen.findByText('/events/e-film', { selector: 'output' })).toBeInTheDocument();
    first.unmount();

    renderApp(new MockApi({ latencyMs: 0, now: () => T0 }), tgWithStart(null));
    expect(await screen.findByText('/', { selector: 'output' })).toBeInTheDocument();
    expect(screen.queryByText('Привет, это «Повод»')).toBeNull();
  });

  it('opens a live reservation remembered on the phone when the server forgot it', async () => {
    const api = new MockApi({ latencyMs: 0, now: () => T0 });
    const detail = await api.event('e-film');
    const order = await api.createOrder('e-film', [{ ticketTypeId: detail.ticketTypes[0].id, qty: 1 }]);
    vi.spyOn(api, 'me').mockResolvedValue({ activeOrder: null, showInAttendees: false });
    const tg = tgWithStart(null);
    await tg.storage.set('activeOrderId', order.id);

    renderApp(api, tg);
    expect(await screen.findByText(`/order/${order.id}`, { selector: 'output' })).toBeInTheDocument();
  });

  it('stays on the screen it was reloaded on when there is no link or reservation', async () => {
    renderApp(new MockApi({ latencyMs: 0, now: () => T0 }), tgWithStart(null), '/favorites');
    expect(await screen.findByRole('link', { name: 'Избранное' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByText('/favorites', { selector: 'output' })).toBeInTheDocument();
  });

  it('sends the old tickets tab to the cabinet', async () => {
    renderApp(new MockApi({ latencyMs: 0, now: () => T0 }), tgWithStart(null), '/tickets');
    expect(await screen.findByText('/me', { selector: 'output' })).toBeInTheDocument();
  });
});

describe('App resilience', () => {
  it('sends an unknown route to the afisha instead of a dead end', async () => {
    renderApp(new MockApi({ latencyMs: 0, now: () => T0 }), tgWithStart(null), '/tgWebAppData=abc&tgWebAppVersion=7');
    expect(await screen.findByText('/', { selector: 'output' })).toBeInTheDocument();
    expect(screen.queryByText('Такой страницы нет')).toBeNull();
  });
});
