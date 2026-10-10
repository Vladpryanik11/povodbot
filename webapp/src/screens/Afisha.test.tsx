import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { buildFixtures } from '../api/mock/fixtures';
import { MockApi } from '../api/mock/MockApi';
import { formatPrice } from '../lib/format';
import { createTg } from '../telegram/tg';
import { renderScreen, T0 } from '../test/render';
import { Afisha } from './Afisha';

describe('Afisha', () => {
  it('puts the nearest evening in the hero with date, seats and price', async () => {
    renderScreen(<Afisha />);
    const hero = await screen.findByTestId('hero');
    expect(within(hero).getByText('Амели на большом экране')).toBeInTheDocument();
    expect(within(hero).getByText('сб, 10 окт · 23:00')).toBeInTheDocument();
    expect(within(hero).getByText('осталось 5 мест')).toBeInTheDocument();
    // Testing Library collapses the page's non-breaking spaces but compares the matcher as is.
    expect(within(hero).getByText(`от ${formatPrice(155000)}`.replace(/\u00a0/g, ' '))).toBeInTheDocument();
    expect(hero.closest('a')).toHaveAttribute('href', '/events/e-film');
  });

  it('filters by direction with a selection haptic', async () => {
    const tg = createTg();
    const selection = vi.spyOn(tg.haptic, 'selection');
    renderScreen(<Afisha />, { tg });
    await userEvent.click(await screen.findByRole('button', { name: 'Мастерклассы' }));
    expect(await screen.findByText('Лепим чашку из глины')).toBeInTheDocument();
    expect(screen.queryByText('Амели на большом экране')).toBeNull();
    expect(selection).toHaveBeenCalled();
  });

  it('marks a sold-out evening', async () => {
    renderScreen(<Afisha />);
    const card = (await screen.findByText('Коктейли без спешки')).closest('a')!;
    expect(card).toHaveAttribute('data-sold-out', 'true');
    expect(within(card).getByText('мест нет')).toBeInTheDocument();
  });

  it('invites to the club chat when nothing is planned', async () => {
    renderScreen(<Afisha />, { api: new MockApi({ scenario: 'empty', latencyMs: 0, now: () => T0 }) });
    expect(await screen.findByText('Пока тихо')).toBeInTheDocument();
    expect(screen.getByText('Новых вечеров нет. Как появятся, напишем в боте.')).toBeInTheDocument();
  });

  it('offers a retry when there is no connection', async () => {
    const api = new MockApi({ scenario: 'offline', latencyMs: 0, now: () => T0 });
    const events = vi.spyOn(api, 'events');
    renderScreen(<Afisha />, { api });
    expect(await screen.findByText('Нет связи')).toBeInTheDocument();
    const calls = events.mock.calls.length;
    await userEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    expect(events.mock.calls.length).toBeGreaterThan(calls);
  });

  it('reminds about a reservation waiting for payment', async () => {
    const api = new MockApi({ latencyMs: 0, now: () => T0 + 18_000 });
    const detail = await api.event('e-film');
    const order = await api.createOrder('e-film', [{ ticketTypeId: detail.ticketTypes[0].id, qty: 1 }]);
    renderScreen(<Afisha />, { api });
    const plaque = await screen.findByRole('link', { name: /Бронь ждёт оплаты · \d\d:\d\d/ });
    expect(plaque).toHaveAttribute('href', `/order/${order.id}`);
  });

  it('shrinks very long titles so cards keep their shape', async () => {
    const fixtures = buildFixtures(T0);
    fixtures.events[1].title = 'Очень длинное название вечера настольных игр, которое не помещается в две строки';
    renderScreen(<Afisha />, { api: new MockApi({ latencyMs: 0, now: () => T0, fixtures }) });
    const title = await screen.findByText(fixtures.events[1].title);
    expect(title).toHaveAttribute('data-long', 'true');
  });
});
