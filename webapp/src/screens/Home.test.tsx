import { act, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { buildFixtures } from '../api/mock/fixtures';
import { MockApi } from '../api/mock/MockApi';
import { renderScreen, T0 } from '../test/render';
import { Home } from './Home';

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(T0);
  localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
});

const billboard = () => screen.getByRole('region', { name: 'Главное' });

describe('Home', () => {
  it('opens with the nearest evening on the billboard and two rows below', async () => {
    renderScreen(<Home />);
    expect(await screen.findByRole('heading', { name: 'На этой неделе' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Скоро' })).toBeInTheDocument();
    const current = billboard().querySelector('[data-current]')!;
    expect(within(current as HTMLElement).getByText('Амели на большом экране')).toBeInTheDocument();
    expect(within(current as HTMLElement).getByText('Сегодня в 23:00')).toBeInTheDocument();
    expect(within(current as HTMLElement).getByText('Киновечер · 18+')).toBeInTheDocument();
    expect(within(billboard()).getAllByRole('tab')).toHaveLength(3);
  });

  it('moves the billboard on by itself every six seconds', async () => {
    renderScreen(<Home />);
    await screen.findByRole('heading', { name: 'Скоро' });
    act(() => vi.advanceTimersByTime(6000));
    const current = billboard().querySelector('[data-current]') as HTMLElement;
    expect(within(current).getByText('Лепим чашку из глины')).toBeInTheDocument();
  });

  it('keeps only the chosen direction everywhere', async () => {
    renderScreen(<Home />);
    await userEvent.click(await screen.findByRole('radio', { name: 'Книжный клуб' }));
    expect(screen.getAllByText('Книжный клуб: «Мастер и Маргарита»').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Книжный клуб: Пелевин и чай').length).toBeGreaterThan(0);
    expect(screen.queryByText('Амели на большом экране')).toBeNull();
    expect(screen.queryByText('Лепим чашку из глины')).toBeNull();
  });

  it('says it is quiet when nothing is planned, without pagination', async () => {
    renderScreen(<Home />, { api: new MockApi({ scenario: 'empty', latencyMs: 0, now: () => T0 }) });
    expect(await screen.findByText('Пока тихо')).toBeInTheDocument();
    expect(screen.getByText('Новых вечеров нет. Как появятся — маякнём в боте.')).toBeInTheDocument();
    expect(screen.queryByRole('tablist')).toBeNull();
  });

  it('shows a single evening without dots', async () => {
    const fixtures = buildFixtures(T0);
    fixtures.events = [fixtures.events[0]];
    renderScreen(<Home />, { api: new MockApi({ latencyMs: 0, now: () => T0, fixtures }) });
    expect(await screen.findByRole('region', { name: 'Главное' })).toBeInTheDocument();
    expect(screen.queryByRole('tablist')).toBeNull();
  });

  it('offers a retry when there is no connection', async () => {
    renderScreen(<Home />, { api: new MockApi({ scenario: 'offline', latencyMs: 0, now: () => T0 }) });
    expect(await screen.findByText('Нет связи')).toBeInTheDocument();
    expect(screen.getByText('Проверь интернет. Купленные билеты никуда не денутся.')).toBeInTheDocument();
  });

  it('reminds about a reservation waiting for payment', async () => {
    const api = new MockApi({ latencyMs: 0, now: () => T0 });
    const detail = await api.event('e-film');
    const order = await api.createOrder('e-film', [{ ticketTypeId: detail.ticketTypes[0].id, qty: 1 }]);
    renderScreen(<Home />, { api });
    const plaque = await screen.findByRole('link', { name: /Бронь ждёт оплаты/ });
    expect(plaque).toHaveAttribute('href', `/order/${order.id}`);
  });
});
