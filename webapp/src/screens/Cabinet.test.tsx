import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MockApi } from '../api/mock/MockApi';
import { ticketCache } from '../lib/ticketCache';
import { createTg, type TelegramWebApp } from '../telegram/tg';
import { renderScreen, T0 } from '../test/render';
import { Cabinet } from './Cabinet';

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(T0);
  localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
});

const withUser = () =>
  createTg({ colorScheme: 'dark', initDataUnsafe: { user: { first_name: 'Аня' } } } as unknown as TelegramWebApp);

describe('Cabinet', () => {
  it('without a Telegram user shows an initial instead of the avatar', async () => {
    renderScreen(<Cabinet />, { at: '/me' });
    expect(await screen.findByRole('heading', { level: 1, name: 'Гость' })).toBeInTheDocument();
    expect(screen.getByText('Г')).toBeInTheDocument();
  });

  it('shows the name, the evenings count and the one valid ticket in the fan', async () => {
    renderScreen(<Cabinet />, { at: '/me', tg: withUser() });
    expect(await screen.findByRole('heading', { level: 1, name: 'Аня' })).toBeInTheDocument();
    expect(screen.getByText('1 вечер с нами')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Мои билеты' })).toBeInTheDocument();
    const fan = await screen.findByRole('region', { name: 'Билеты' });
    expect(fan.querySelectorAll('article')).toHaveLength(1);
    expect(within(fan).getByText('Номер 4821')).toBeInTheDocument();
    expect(screen.getByText('Прошедшие · 3')).toBeInTheDocument();
  });

  it('opens the ticket from the fan', async () => {
    renderScreen(<Cabinet />, { at: '/me' });
    const fan = await screen.findByRole('region', { name: 'Билеты' });
    await userEvent.click(within(fan).getByText('Номер 4821'));
    expect(await screen.findByText('/tickets/tk-1', { selector: 'output' })).toBeInTheDocument();
  });

  it('keeps used tickets as torn souvenirs in «Мои вечера»', async () => {
    renderScreen(<Cabinet />, { at: '/me' });
    const evenings = await screen.findByRole('region', { name: 'Мои вечера' });
    expect(within(evenings).getByText(/^Было · /)).toBeInTheDocument();
    expect(within(evenings).queryByTestId('stub')).toBeNull();
  });

  it('invites to the home screen when there are no tickets', async () => {
    renderScreen(<Cabinet />, { at: '/me', api: new MockApi({ scenario: 'empty', latencyMs: 0, now: () => T0 }) });
    expect(await screen.findByText('Билетов пока нет')).toBeInTheDocument();
    expect(screen.getByText('Выбери вечер на главной — билет появится здесь.')).toBeInTheDocument();
  });

  it('writes to the organiser in the bot', async () => {
    const tg = createTg();
    const open = vi.spyOn(tg, 'openTelegramLink').mockImplementation(() => undefined);
    renderScreen(<Cabinet />, { at: '/me', tg });
    await userEvent.click(await screen.findByRole('button', { name: 'Написать организатору' }));
    expect(open).toHaveBeenCalledWith('https://t.me/povod_club_bot');
  });

  it('explains how to return a ticket', async () => {
    renderScreen(<Cabinet />, { at: '/me' });
    await userEvent.click(await screen.findByRole('button', { name: 'Как вернуть билет' }));
    expect(await screen.findByRole('dialog', { name: 'Как вернуть билет' })).toBeInTheDocument();
  });

  it('the privacy switch turns on showing me among the guests', async () => {
    const api = new MockApi({ latencyMs: 0, now: () => T0 });
    renderScreen(<Cabinet />, { at: '/me', api });
    const toggle = await screen.findByRole('switch', { name: 'Показывать меня в списке гостей' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    await userEvent.click(toggle);
    expect((await api.me()).showInAttendees).toBe(true);
    expect(await screen.findByRole('switch', { name: 'Показывать меня в списке гостей', checked: true })).toBeInTheDocument();
  });

  it('shows saved tickets right away while the server is slow', async () => {
    const online = new MockApi({ latencyMs: 0, now: () => T0 });
    ticketCache.save(await online.tickets());
    renderScreen(<Cabinet />, { at: '/me', api: new MockApi({ latencyMs: 60_000, now: () => T0 }) });
    const fan = await screen.findByRole('region', { name: 'Билеты' });
    expect(within(fan).getByText('Номер 4821')).toBeInTheDocument();
  });
});
