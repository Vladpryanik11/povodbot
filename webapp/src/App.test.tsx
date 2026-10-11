import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
  it('greets once, then keeps the deep link', async () => {
    const api = new MockApi({ latencyMs: 0, now: () => T0 });
    const accept = vi.spyOn(api, 'acceptWelcome');
    const first = renderApp(api, tgWithStart('event_e-film'));

    expect(await screen.findByText('Привет, это «Повод»')).toBeInTheDocument();
    expect(
      screen.getByText('Маленький клуб в Москве: киновечера, мастерклассы и книжный клуб для своих. Выбирай вечер, бери билет — и увидимся.'),
    ).toBeInTheDocument();
    expect(await screen.findByText('Амели на большом экране')).toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: 'Заходим' }));
    expect(accept).toHaveBeenCalledTimes(1);
    expect(await screen.findByText('/events/e-film', { selector: 'output' })).toBeInTheDocument();
    first.unmount();

    renderApp(new MockApi({ latencyMs: 0, now: () => T0 }), tgWithStart(null));
    expect(await screen.findByText('/', { selector: 'output' })).toBeInTheDocument();
    expect(screen.queryByText('Привет, это «Повод»')).toBeNull();
  });

  it('opens a live reservation remembered on the phone when the server forgot it', async () => {
    localStorage.setItem('povod.mock.welcome', '1');
    const api = new MockApi({ latencyMs: 0, now: () => T0 });
    const detail = await api.event('e-film');
    const order = await api.createOrder('e-film', [{ ticketTypeId: detail.ticketTypes[0].id, qty: 1 }]);
    vi.spyOn(api, 'me').mockResolvedValue({ welcomeAccepted: true, activeOrder: null, showInAttendees: false });
    const tg = tgWithStart(null);
    await tg.storage.set('activeOrderId', order.id);

    renderApp(api, tg);
    expect(await screen.findByText(`/order/${order.id}`, { selector: 'output' })).toBeInTheDocument();
  });

  it('stays on the screen it was reloaded on when there is no link or reservation', async () => {
    localStorage.setItem('povod.mock.welcome', '1');
    renderApp(new MockApi({ latencyMs: 0, now: () => T0 }), tgWithStart(null), '/favorites');
    expect(await screen.findByRole('link', { name: 'Избранное' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByText('/favorites', { selector: 'output' })).toBeInTheDocument();
  });

  it('sends the old tickets tab to the cabinet', async () => {
    localStorage.setItem('povod.mock.welcome', '1');
    renderApp(new MockApi({ latencyMs: 0, now: () => T0 }), tgWithStart(null), '/tickets');
    expect(await screen.findByText('/me', { selector: 'output' })).toBeInTheDocument();
  });
});

describe('App resilience', () => {
  it('sends an unknown route to the afisha instead of a dead end', async () => {
    localStorage.setItem('povod.mock.welcome', '1');
    renderApp(new MockApi({ latencyMs: 0, now: () => T0 }), tgWithStart(null), '/tgWebAppData=abc&tgWebAppVersion=7');
    expect(await screen.findByText('/', { selector: 'output' })).toBeInTheDocument();
    expect(screen.queryByText('Такой страницы нет')).toBeNull();
  });

  it('tells the guest when accepting the welcome fails', async () => {
    const api = new MockApi({ latencyMs: 0, now: () => T0 });
    vi.spyOn(api, 'acceptWelcome').mockRejectedValue(new Error('offline'));
    renderApp(api, tgWithStart(null));
    await userEvent.click(await screen.findByRole('button', { name: 'Заходим' }));
    expect(await screen.findByText('Не получилось. Проверь интернет и попробуй ещё раз.')).toBeInTheDocument();
  });
});
