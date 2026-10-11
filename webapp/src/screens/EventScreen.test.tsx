import { act, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/AppApi';
import { buildFixtures } from '../api/mock/fixtures';
import { MockApi } from '../api/mock/MockApi';
import { createTg } from '../telegram/tg';
import { renderScreen, T0 } from '../test/render';
import { EventScreen } from './EventScreen';

const at = (id: string) => ({ at: `/events/${id}`, path: '/events/:id' });
const add = () => userEvent.click(screen.getByRole('button', { name: /Входной: .*Добавить/ }));

describe('EventScreen', () => {
  it('shows a preview without loading or buying', async () => {
    const api = new MockApi({ latencyMs: 0, now: () => T0 });
    const detail = await api.event('e-film');
    const event = vi.spyOn(api, 'event');
    const createOrder = vi.spyOn(api, 'createOrder');
    renderScreen(<EventScreen preview={detail} />, { ...at('x'), api });
    expect(screen.getByText('Так увидит гость')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Амели на большом экране' })).toBeInTheDocument();
    await add();
    expect(screen.getByRole('button', { name: /Купить/ })).toBeDisabled();
    expect(event).not.toHaveBeenCalled();
    expect(createOrder).not.toHaveBeenCalled();
  });

  it('starts the bottom bar at the lowest price, then sums the cart there', async () => {
    renderScreen(<EventScreen />, at('e-film'));
    expect(await screen.findByRole('heading', { name: 'Амели на большом экране' })).toBeInTheDocument();
    expect(await screen.findByText('от 1 550 ₽')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Купить' })).toBeEnabled();
    await add();
    await add();
    expect(await screen.findByText('2 билета · 3 100 ₽')).toBeInTheDocument();
    expect(screen.queryByText('от 1 550 ₽')).toBeNull();
    expect(screen.getByRole('button', { name: 'Купить' })).toBeEnabled();
  });

  it('with no tickets picked, «Купить» leads to the tickets block instead of buying', async () => {
    const api = new MockApi({ latencyMs: 0, now: () => T0 });
    const createOrder = vi.spyOn(api, 'createOrder');
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    renderScreen(<EventScreen />, { ...at('e-film'), api });
    await userEvent.click(await screen.findByRole('button', { name: 'Купить' }));
    expect(scroll).toHaveBeenCalledTimes(1);
    expect(scroll.mock.contexts[0]).toBe(screen.getByRole('region', { name: 'Билеты' }));
    expect(createOrder).not.toHaveBeenCalled();
  });

  it('says there are no seats for a sold-out evening', async () => {
    renderScreen(<EventScreen />, at('e-workshop-2'));
    expect(await screen.findByRole('button', { name: 'Мест нет' })).toBeDisabled();
    expect(screen.queryByText(/^от /)).toBeNull();
  });

  it('has no poll block any more', async () => {
    renderScreen(<EventScreen />, at('e-film'));
    await screen.findByRole('heading', { name: 'Амели на большом экране' });
    expect(screen.queryByText('Что смотрим в пятницу?')).toBeNull();
  });

  it('shows the poster header: back, heart, direction, date', async () => {
    renderScreen(<EventScreen />, at('e-film'));
    const title = await screen.findByRole('heading', { level: 1, name: 'Амели на большом экране' });
    const header = title.closest('header')!;
    expect(await within(header).findByText('Киновечер · 18+')).toBeInTheDocument();
    expect(within(header).getByText('сб, 10 окт · 23:00')).toBeInTheDocument();
    expect(within(header).getByRole('button', { name: 'В избранное' })).toBeInTheDocument();
    expect(within(header).getByRole('button', { name: 'Назад' })).toBeInTheDocument();
  });

  it('gives the address with a route link, or promises it in the bot', async () => {
    const tg = createTg();
    const openLink = vi.spyOn(tg, 'openLink').mockImplementation(() => undefined);
    renderScreen(<EventScreen />, { ...at('e-film'), tg });
    await userEvent.click(await screen.findByRole('link', { name: 'Построить маршрут' }));
    expect(openLink).toHaveBeenCalledWith(expect.stringContaining('http'));
    renderScreen(<EventScreen />, at('e-book'));
    expect(await screen.findByText('Адрес пришлём в бот')).toBeInTheDocument();
  });

  it('creates one order on a double tap, keeps the phone-side id and opens the bank page', async () => {
    const api = new MockApi({ latencyMs: 30, now: () => T0 });
    const createOrder = vi.spyOn(api, 'createOrder');
    const tg = createTg();
    const openLink = vi.spyOn(tg, 'openLink').mockImplementation(() => undefined);
    const closing = vi.spyOn(tg, 'closingConfirmation');
    renderScreen(<EventScreen />, { ...at('e-film'), api, tg });
    await screen.findByRole('heading', { name: 'Амели на большом экране' });
    await add();
    const pay = await screen.findByRole('button', { name: 'Купить' });
    await userEvent.dblClick(pay);
    expect(await screen.findByText('/order/o-1', { selector: 'output' })).toBeInTheDocument();
    expect(createOrder).toHaveBeenCalledTimes(1);
    expect(openLink).toHaveBeenCalledWith('#/mock-pay/o-1');
    expect(closing).toHaveBeenCalledWith(true);
    expect(await tg.storage.get('activeOrderId')).toBe('o-1');
  });

  it('sends the guest to the bot while buying in the app is closed', async () => {
    const api = new MockApi({ latencyMs: 0, now: () => T0 });
    vi.spyOn(api, 'createOrder').mockRejectedValue(new ApiError('sales_closed'));
    renderScreen(<EventScreen />, { ...at('e-film'), api });
    await screen.findByRole('heading', { name: 'Амели на большом экране' });
    await add();
    await userEvent.click(await screen.findByRole('button', { name: 'Купить' }));
    expect(await screen.findByRole('dialog', { name: 'Билеты — в чате бота' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Понятно' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('offers to continue an existing reservation', async () => {
    const api = new MockApi({ latencyMs: 0, now: () => T0 });
    const detail = await api.event('e-workshop');
    await api.createOrder('e-workshop', [{ ticketTypeId: detail.ticketTypes[0].id, qty: 1 }]);
    renderScreen(<EventScreen />, { ...at('e-film'), api });
    await screen.findByRole('heading', { name: 'Амели на большом экране' });
    await add();
    await userEvent.click(await screen.findByRole('button', { name: 'Купить' }));
    expect(await screen.findByRole('dialog', { name: 'У тебя уже есть бронь' })).toBeInTheDocument();
    expect(screen.getByText('Бронь на «Лепим чашку из глины» ждёт оплаты. Продолжить оплату или отменить?')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Продолжить' }));
    expect(await screen.findByText('/order/o-1', { selector: 'output' })).toBeInTheDocument();
  });

  it('shrinks the order when seats ran out while the guest was choosing', async () => {
    const api = new MockApi({ scenario: 'sold_out', latencyMs: 0, now: () => T0 });
    const createOrder = vi.spyOn(api, 'createOrder');
    const tg = createTg();
    vi.spyOn(tg, 'openLink').mockImplementation(() => undefined);
    const notify = vi.spyOn(tg.haptic, 'notify');
    renderScreen(<EventScreen />, { ...at('e-film'), api, tg });
    await screen.findByRole('heading', { name: 'Амели на большом экране' });
    await add();
    await add();
    await add();
    await userEvent.click(await screen.findByRole('button', { name: 'Купить' }));
    expect(await screen.findByRole('dialog', { name: 'Мест стало меньше' })).toBeInTheDocument();
    expect(screen.getByText('Пока шёл выбор, осталось 2 места. Берём 2?')).toBeInTheDocument();
    expect(notify).toHaveBeenCalledWith('warning');
    await act(() => userEvent.click(screen.getByRole('button', { name: 'Берём 2' })));
    expect(await screen.findByText('/order/o-1', { selector: 'output' })).toBeInTheDocument();
    expect(createOrder).toHaveBeenLastCalledWith('e-film', [{ ticketTypeId: 'tt-film', qty: 2 }]);
  });

  it('gives a light haptic on every step', async () => {
    const tg = createTg();
    const impact = vi.spyOn(tg.haptic, 'impact');
    renderScreen(<EventScreen />, { ...at('e-film'), tg });
    await screen.findByRole('heading', { name: 'Амели на большом экране' });
    await add();
    expect(impact).toHaveBeenCalledWith('light');
  });
});

describe('EventScreen edge cases', () => {
  it('marks a very long title so it shrinks and wraps', async () => {
    const fixtures = buildFixtures(T0);
    fixtures.events[0].title = 'Интеллектуальная викторина о самом главном в нашем городе';
    renderScreen(<EventScreen />, { ...at('e-film'), api: new MockApi({ latencyMs: 0, now: () => T0, fixtures }) });
    expect(await screen.findByRole('heading', { name: fixtures.events[0].title })).toHaveAttribute('data-long', 'true');
  });

  it('explains an evening that no longer exists and leads to the afisha', async () => {
    renderScreen(<EventScreen />, at('e-gone'));
    expect(await screen.findByText('Вечер не найден')).toBeInTheDocument();
    expect(screen.queryByText('Нет связи')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'На главную' }));
    expect(await screen.findByText('/', { selector: 'output' })).toBeInTheDocument();
  });
});
