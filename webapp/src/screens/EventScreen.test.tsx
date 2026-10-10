import { act, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { MockApi } from '../api/mock/MockApi';
import { createTg } from '../telegram/tg';
import { renderScreen, T0 } from '../test/render';
import { EventScreen } from './EventScreen';

const at = (id: string) => ({ at: `/events/${id}`, path: '/events/:id' });
const add = () => userEvent.click(screen.getByRole('button', { name: /Входной: .*Добавить/ }));

describe('EventScreen', () => {
  it('sums the cart and puts the total on the main button', async () => {
    renderScreen(<EventScreen />, at('e-film'));
    expect(await screen.findByRole('heading', { name: 'Повод для киновечера' })).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Выберите билеты' })).toBeDisabled();
    await add();
    await add();
    await add();
    expect(screen.getByText('3 билета · 4 650 ₽')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /^Оплатить 4\s650\s₽$/ })).toBeEnabled();
  });

  it('says there are no seats for a sold-out evening', async () => {
    renderScreen(<EventScreen />, at('e-party'));
    expect(await screen.findByRole('button', { name: 'Мест нет' })).toBeDisabled();
  });

  it('shows the poll question and the undecided venue', async () => {
    renderScreen(<EventScreen />, at('e-film'));
    expect(await screen.findByText('Что смотрим в пятницу?')).toBeInTheDocument();
    renderScreen(<EventScreen />, at('e-talk'));
    expect(
      await screen.findByText('Место пока уточняется. Напишем в боте, как только определимся.'),
    ).toBeInTheDocument();
  });

  it('creates one order on a double tap, keeps the phone-side id and opens the bank page', async () => {
    const api = new MockApi({ latencyMs: 30, now: () => T0 });
    const createOrder = vi.spyOn(api, 'createOrder');
    const tg = createTg();
    const openLink = vi.spyOn(tg, 'openLink').mockImplementation(() => undefined);
    const closing = vi.spyOn(tg, 'closingConfirmation');
    renderScreen(<EventScreen />, { ...at('e-film'), api, tg });
    await screen.findByRole('heading', { name: 'Повод для киновечера' });
    await add();
    const pay = await screen.findByRole('button', { name: /^Оплатить/ });
    await userEvent.dblClick(pay);
    expect(await screen.findByText('/order/o-1', { selector: 'output' })).toBeInTheDocument();
    expect(createOrder).toHaveBeenCalledTimes(1);
    expect(openLink).toHaveBeenCalledWith('#/mock-pay/o-1');
    expect(closing).toHaveBeenCalledWith(true);
    expect(await tg.storage.get('activeOrderId')).toBe('o-1');
  });

  it('offers to continue an existing reservation', async () => {
    const api = new MockApi({ latencyMs: 0, now: () => T0 });
    const detail = await api.event('e-games');
    await api.createOrder('e-games', [{ ticketTypeId: detail.ticketTypes[0].id, qty: 1 }]);
    renderScreen(<EventScreen />, { ...at('e-film'), api });
    await screen.findByRole('heading', { name: 'Повод для киновечера' });
    await add();
    await userEvent.click(await screen.findByRole('button', { name: /^Оплатить/ }));
    expect(await screen.findByRole('dialog', { name: 'У вас уже есть бронь' })).toBeInTheDocument();
    expect(screen.getByText('Бронь на «Настолки до утра» ждёт оплаты. Продолжить оплату или отменить?')).toBeInTheDocument();
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
    await screen.findByRole('heading', { name: 'Повод для киновечера' });
    await add();
    await add();
    await add();
    await userEvent.click(await screen.findByRole('button', { name: /^Оплатить/ }));
    expect(await screen.findByRole('dialog', { name: 'Мест стало меньше' })).toBeInTheDocument();
    expect(screen.getByText('Пока вы выбирали, осталось 2 места. Взять 2 билета?')).toBeInTheDocument();
    expect(notify).toHaveBeenCalledWith('warning');
    await act(() => userEvent.click(screen.getByRole('button', { name: 'Взять 2' })));
    expect(await screen.findByText('/order/o-1', { selector: 'output' })).toBeInTheDocument();
    expect(createOrder).toHaveBeenLastCalledWith('e-film', [{ ticketTypeId: 'tt-film', qty: 2 }]);
  });

  it('gives a light haptic on every step', async () => {
    const tg = createTg();
    const impact = vi.spyOn(tg.haptic, 'impact');
    renderScreen(<EventScreen />, { ...at('e-film'), tg });
    await screen.findByRole('heading', { name: 'Повод для киновечера' });
    await add();
    expect(impact).toHaveBeenCalledWith('light');
  });
});
