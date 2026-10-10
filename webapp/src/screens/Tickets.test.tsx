import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MockApi } from '../api/mock/MockApi';
import { ticketCache } from '../lib/ticketCache';
import { createTg } from '../telegram/tg';
import { renderScreen, T0 } from '../test/render';
import { ClaimScreen } from './ClaimScreen';
import { Tickets } from './Tickets';
import { TicketScreen } from './TicketScreen';

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(T0);
});

afterEach(() => {
  vi.useRealTimers();
});

const ticketAt = (id: string) => ({ at: `/tickets/${id}`, path: '/tickets/:id' });

describe('Tickets list', () => {
  it('groups upcoming tickets by evening and folds the past', async () => {
    renderScreen(<Tickets />, { at: '/tickets' });
    expect(await screen.findByRole('heading', { name: 'Ближайшие' })).toBeInTheDocument();
    const film = screen.getByRole('link', { name: /Повод для киновечера/ });
    expect(within(film).getByText('2 билета')).toBeInTheDocument();
    expect(film).toHaveAttribute('href', '/tickets/tk-1');
    expect(screen.getByText('Прошедшие · 2')).toBeInTheDocument();
    expect(screen.getByText('Передан')).toBeInTheDocument();
    expect(screen.getByText('Возвращён')).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: 'QR-код билета' })).toBeNull();
  });

  it('invites to the afisha when there are no tickets', async () => {
    renderScreen(<Tickets />, { at: '/tickets', api: new MockApi({ scenario: 'empty', latencyMs: 0, now: () => T0 }) });
    expect(await screen.findByText('Билетов пока нет')).toBeInTheDocument();
    expect(screen.getByText('Выберите вечер в афише — билеты появятся здесь.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Открыть афишу' }));
    expect(await screen.findByText('/', { selector: 'output' })).toBeInTheDocument();
  });
});

describe('Ticket screen', () => {
  it('shows a large QR with the fallback number and pages to the next ticket', async () => {
    const tg = createTg();
    const openLink = vi.spyOn(tg, 'openLink').mockImplementation(() => undefined);
    renderScreen(<TicketScreen />, { ...ticketAt('tk-1'), tg });
    const qr = await screen.findByRole('img', { name: 'QR-код билета' });
    expect(parseInt(qr.style.width, 10)).toBeGreaterThanOrEqual(240);
    expect(screen.getByText('Билет 1 из 2')).toBeInTheDocument();
    expect(screen.getByText('Покажите QR на входе')).toBeInTheDocument();
    expect(screen.getByText('Номер 4821 — если QR не читается')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Следующий билет' }));
    expect(await screen.findByText('Билет 2 из 2')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'На карте' }));
    expect(openLink).toHaveBeenCalledWith(expect.stringContaining('yandex.ru/maps'));
  });

  it('never shows a QR for a transferred ticket', async () => {
    renderScreen(<TicketScreen />, ticketAt('tk-3'));
    expect(await screen.findByText('Передан')).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: 'QR-код билета' })).toBeNull();
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
    const api = new MockApi({ latencyMs: 0, now: () => T0 });
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

describe('Claim screen', () => {
  it('gives the ticket to the friend once and explains a second attempt', async () => {
    const api = new MockApi({ latencyMs: 0, now: () => T0 });
    const { shareUrl } = await api.shareTicket('tk-2');
    const token = new URL(shareUrl).searchParams.get('startapp')!.replace('claim_', '');
    const first = renderScreen(<ClaimScreen />, { api, at: `/claim/${token}`, path: '/claim/:token' });
    expect(await screen.findByText('Билет ваш')).toBeInTheDocument();
    first.unmount();
    renderScreen(<ClaimScreen />, { api, at: `/claim/${token}`, path: '/claim/:token' });
    expect(await screen.findByText('Этот билет уже забрал другой гость')).toBeInTheDocument();
  });
});
