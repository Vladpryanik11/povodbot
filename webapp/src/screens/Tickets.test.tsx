import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { buildFixtures } from '../api/mock/fixtures';
import { MockApi } from '../api/mock/MockApi';
import { ticketCache } from '../lib/ticketCache';
import { renderScreen, T0 } from '../test/render';
import { ClaimScreen } from './ClaimScreen';
import { Tickets } from './Tickets';

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(T0);
});

afterEach(() => {
  vi.useRealTimers();
});


/** The default fixtures hold one valid ticket; these screens need a pair from one order. */
function withPair(): MockApi {
  const fixtures = buildFixtures(T0);
  const first = fixtures.tickets[0];
  first.ofCount = 2;
  fixtures.tickets.splice(1, 0, { ...first, id: 'tk-2', position: 2, shortCode: '4822', qrToken: 'pv1.tk-2.ZGVtby1zZWNvbmQtdGlja2V0' });
  return new MockApi({ latencyMs: 0, now: () => T0, fixtures });
}

describe('Tickets list', () => {
  it('groups upcoming tickets by evening and folds the past', async () => {
    renderScreen(<Tickets />, { at: '/tickets', api: withPair() });
    expect(await screen.findByRole('heading', { name: 'Ближайшие' })).toBeInTheDocument();
    const film = screen.getByRole('link', { name: /Амели на большом экране/ });
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

describe('Claim screen', () => {
  it('gives the ticket to the friend once and explains a second attempt', async () => {
    const api = withPair();
    const { shareUrl } = await api.shareTicket('tk-2');
    const token = new URL(shareUrl).searchParams.get('startapp')!.replace('claim_', '');
    const first = renderScreen(<ClaimScreen />, { api, at: `/claim/${token}`, path: '/claim/:token' });
    expect(await screen.findByText('Билет ваш')).toBeInTheDocument();
    first.unmount();
    renderScreen(<ClaimScreen />, { api, at: `/claim/${token}`, path: '/claim/:token' });
    expect(await screen.findByText('Этот билет уже забрал другой гость')).toBeInTheDocument();
  });
});

describe('Tickets from the phone', () => {
  it('shows saved tickets right away while the server is slow', async () => {
    const online = new MockApi({ latencyMs: 0, now: () => T0 });
    ticketCache.save(await online.tickets());
    renderScreen(<Tickets />, { at: '/tickets', api: new MockApi({ latencyMs: 60_000, now: () => T0 }) });
    expect(await screen.findByRole('heading', { name: 'Ближайшие' })).toBeInTheDocument();
  });
});
