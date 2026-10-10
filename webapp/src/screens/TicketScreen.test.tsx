import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { buildFixtures } from '../api/mock/fixtures';
import { MockApi } from '../api/mock/MockApi';
import { ticketCache } from '../lib/ticketCache';
import { createTg, type TelegramWebApp } from '../telegram/tg';
import { renderScreen, T0 } from '../test/render';
import { TicketScreen } from './TicketScreen';

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(T0);
  localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
});

const ticketAt = (id: string) => ({ at: `/tickets/${id}`, path: '/tickets/:id' });

/** The default fixtures hold one valid ticket; these cases need a pair from one order. */
function withPair(): MockApi {
  const fixtures = buildFixtures(T0);
  const first = fixtures.tickets[0];
  first.ofCount = 2;
  fixtures.tickets.splice(1, 0, { ...first, id: 'tk-2', position: 2, shortCode: '4822', qrToken: 'pv1.tk-2.ZGVtby1zZWNvbmQtdGlja2V0' });
  return new MockApi({ latencyMs: 0, now: () => T0, fixtures });
}

const current = () => screen.getByRole('region', { name: 'Билеты' }).querySelector<HTMLElement>('[data-current]')!;

describe('Ticket screen', () => {
  it('shows the paper ticket with a large QR, the guest name, and fans out to the next one', async () => {
    const web = { colorScheme: 'dark', initDataUnsafe: { user: { first_name: 'Аня' } } } as unknown as TelegramWebApp;
    const tg = createTg(web);
    const openLink = vi.spyOn(tg, 'openLink').mockImplementation(() => undefined);
    renderScreen(<TicketScreen />, { ...ticketAt('tk-1'), api: withPair(), tg });
    const qr = await within(await screen.findByRole('region', { name: 'Билеты' })).findAllByRole('img', { name: 'QR-код билета' });
    expect(parseInt(qr[0].style.width, 10)).toBeGreaterThanOrEqual(240);
    expect(within(current()).getByText('Билет 1 из 2')).toBeInTheDocument();
    expect(within(current()).getByText('Номер 4821')).toBeInTheDocument();
    expect(within(current()).getByText('Аня')).toBeInTheDocument();
    screen.getByRole('region', { name: 'Билеты' }).focus();
    await userEvent.keyboard('{ArrowRight}');
    expect(await screen.findByText('/tickets/tk-2', { selector: 'output' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Построить маршрут' }));
    expect(openLink).toHaveBeenCalledWith(expect.stringContaining('yandex.ru/maps'));
  });

  it('never shows a QR for a transferred ticket', async () => {
    renderScreen(<TicketScreen />, ticketAt('tk-3'));
    expect(await screen.findByText('Передан')).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: 'QR-код билета' })).toBeNull();
  });

  it('tears the stub off a used ticket once, the first time it is shown', async () => {
    const tg = createTg();
    const first = renderScreen(<TicketScreen />, { ...ticketAt('tk-4'), tg });
    expect(await screen.findByText('Было · 20 сент')).toBeInTheDocument();
    expect(await screen.findByTestId('stub')).toHaveAttribute('data-tearing');
    await vi.waitFor(async () => expect(await tg.storage.get('torn:tk-4')).toBe('1'));
    first.unmount();
    renderScreen(<TicketScreen />, { ...ticketAt('tk-4'), tg });
    expect(await screen.findByText('Было · 20 сент')).toBeInTheDocument();
    expect(screen.queryByTestId('stub')).toBeNull();
  });

  it('opens from the phone when there is no connection', async () => {
    const online = new MockApi({ latencyMs: 0, now: () => T0 });
    ticketCache.save(await online.tickets());
    renderScreen(<TicketScreen />, {
      ...ticketAt('tk-1'),
      api: new MockApi({ scenario: 'offline', latencyMs: 0, now: () => T0 }),
    });
    expect(await screen.findByRole('img', { name: 'QR-код билета' })).toBeInTheDocument();
    expect(screen.getByText('Билет сохранён на телефоне')).toBeInTheDocument();
  });

  it('sends a ticket to a friend through the Telegram share sheet', async () => {
    const api = withPair();
    const tg = createTg();
    const share = vi.spyOn(tg, 'openTelegramLink').mockImplementation(() => undefined);
    renderScreen(<TicketScreen />, { ...ticketAt('tk-2'), api, tg });
    await userEvent.click(await screen.findByRole('button', { name: 'Отправить другу' }));
    expect(share).toHaveBeenCalledTimes(1);
    const url = new URL(share.mock.calls[0][0]);
    expect(url.origin + url.pathname).toBe('https://t.me/share/url');
    expect(url.searchParams.get('url')).toMatch(/startapp=claim_/);
  });
});
