import { act, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/AppApi';
import { MockApi, type Scenario } from '../api/mock/MockApi';
import { ticketCache } from '../lib/ticketCache';
import { createTg } from '../telegram/tg';
import { renderScreen, T0 } from '../test/render';
import { OrderScreen } from './OrderScreen';

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(T0);
});

afterEach(() => {
  vi.useRealTimers();
});

async function setup(scenario: Scenario = 'happy', pay?: 'paid' | 'failed') {
  const api = new MockApi({ scenario, latencyMs: 0 });
  const detail = await api.event('e-film');
  const order = await api.createOrder('e-film', [{ ticketTypeId: detail.ticketTypes[0].id, qty: 2 }]);
  if (pay) await api.completePayment(order.id, pay);
  const tg = createTg();
  const haptic = vi.spyOn(tg.haptic, 'notify');
  const closing = vi.spyOn(tg, 'closingConfirmation');
  const openLink = vi.spyOn(tg, 'openLink').mockImplementation(() => undefined);
  const back = vi.spyOn(tg.backButton, 'set');
  return { api, tg, order, haptic, closing, openLink, back };
}

function open(ctx: Awaited<ReturnType<typeof setup>>) {
  return renderScreen(<OrderScreen />, { api: ctx.api, tg: ctx.tg, at: `/order/${ctx.order.id}`, path: '/order/:id' });
}

const advance = (ms: number) => act(async () => void vi.advanceTimersByTime(ms));
const user = () => userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
const lastBack = (spy: ReturnType<typeof vi.spyOn>) => spy.mock.calls.filter((c) => c[0]).at(-1)![0] as () => void;

describe('OrderScreen while the reservation waits', () => {
  it('counts down, reopens the payment and cancels on confirmation', async () => {
    const ctx = await setup();
    vi.setSystemTime(T0 + 78_000);
    open(ctx);
    expect(await screen.findByText('Бронь ждёт оплаты')).toBeInTheDocument();
    expect(screen.getByRole('timer')).toHaveTextContent('08:42');
    expect(screen.getByText(/Места за вами ещё/)).toBeInTheDocument();

    await user().click(await screen.findByRole('button', { name: 'Открыть оплату снова' }));
    expect(ctx.openLink).toHaveBeenCalledWith(ctx.order.paymentUrl);

    const cancel = vi.spyOn(ctx.api, 'cancelOrder');
    await user().click(screen.getByRole('button', { name: 'Отменить бронь' }));
    expect(screen.getByRole('dialog', { name: 'Отменить бронь?' })).toHaveTextContent('Места вернутся в продажу.');
    await user().click(screen.getByRole('button', { name: 'Отменить' }));
    expect(cancel).toHaveBeenCalledWith(ctx.order.id);
    expect(ctx.closing).toHaveBeenLastCalledWith(false);
  });

  it('turns into «Бронь закончилась» when the timer runs out on screen', async () => {
    const ctx = await setup();
    open(ctx);
    await screen.findByText('Бронь ждёт оплаты');
    await advance(10 * 60 * 1000 + 1000);
    expect(await screen.findByText('Бронь закончилась')).toBeInTheDocument();
    expect(screen.getByText('Десять минут прошли, места вернулись в продажу.')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Выбрать заново' })).toBeInTheDocument();
    expect(ctx.haptic).toHaveBeenCalledWith('warning');
  });

  it('leads «назад» to the afisha without cancelling', async () => {
    const ctx = await setup();
    const cancel = vi.spyOn(ctx.api, 'cancelOrder');
    open(ctx);
    await screen.findByText('Бронь ждёт оплаты');
    act(() => lastBack(ctx.back)());
    expect(await screen.findByText('/', { selector: 'output' })).toBeInTheDocument();
    expect(cancel).not.toHaveBeenCalled();
  });
});

describe('OrderScreen after the bank', () => {
  it('celebrates a paid order and leads to the tickets', async () => {
    const ctx = await setup('happy', 'paid');
    open(ctx);
    expect(await screen.findByText('Билеты у вас')).toBeInTheDocument();
    expect(screen.getByText('Ждём в сб, 10 окт в 23:00. Копия ушла в бот.')).toBeInTheDocument();
    expect(ctx.haptic).toHaveBeenCalledWith('success');
    expect(ctx.closing).toHaveBeenLastCalledWith(false);
    act(() => lastBack(ctx.back)());
    expect(await screen.findByText('/tickets', { selector: 'output' })).toBeInTheDocument();
  });

  it('opens the tickets from the main button', async () => {
    const ctx = await setup('happy', 'paid');
    open(ctx);
    await user().click(await screen.findByRole('button', { name: 'Показать билеты' }));
    expect(await screen.findByText('/tickets', { selector: 'output' })).toBeInTheDocument();
  });

  it('waits for an uncertain bank without offering to cancel, then explains the delay', async () => {
    const ctx = await setup('pay_pending', 'paid');
    open(ctx);
    expect(await screen.findByText('Ждём подтверждения банка')).toBeInTheDocument();
    expect(screen.getByText('Обычно хватает минуты. Повторно платить не нужно.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Отменить бронь' })).toBeNull();
    await advance(61_000);
    expect(await screen.findByText('Банк отвечает дольше обычного')).toBeInTheDocument();
    expect(
      screen.getByText('Если оплата прошла, билет придёт сообщением в бот. Страницу можно закрыть.'),
    ).toBeInTheDocument();
  });

  it('offers another try while the failed reservation still lives', async () => {
    const ctx = await setup('happy', 'failed');
    vi.setSystemTime(T0 + 4 * 60 * 1000);
    open(ctx);
    expect(await screen.findByText('Оплата не прошла')).toBeInTheDocument();
    expect(screen.getByText('Деньги не списаны. Бронь ещё держим — 6 минут.')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Попробовать снова' })).toBeInTheDocument();
    expect(ctx.haptic).toHaveBeenCalledWith('error');
  });

  it('explains a payment that arrived after the reservation', async () => {
    const ctx = await setup('late', 'paid');
    open(ctx);
    expect(
      await screen.findByText('Оплата дошла после окончания брони. Администратор проверит и напишет вам сегодня.'),
    ).toBeInTheDocument();
  });
});

describe('OrderScreen review fixes', () => {
  it('saves the new tickets on the phone as soon as the order is paid', async () => {
    const ctx = await setup('happy', 'paid');
    open(ctx);
    await screen.findByText('Билеты у вас');
    await advance(100);
    expect(ticketCache.load().filter((t) => t.id.startsWith(`${ctx.order.id}-`))).toHaveLength(2);
  });

  it('keeps asking the server after a failed attempt, so a later payment is noticed', async () => {
    const ctx = await setup('happy', 'failed');
    open(ctx);
    await screen.findByText('Оплата не прошла');
    await ctx.api.completePayment(ctx.order.id, 'paid');
    await advance(3500);
    expect(await screen.findByText('Билеты у вас')).toBeInTheDocument();
  });

  it('says when cancelling the reservation did not work', async () => {
    const ctx = await setup();
    vi.spyOn(ctx.api, 'cancelOrder').mockRejectedValue(new ApiError('network'));
    open(ctx);
    await user().click(await screen.findByRole('button', { name: 'Отменить бронь' }));
    await user().click(screen.getByRole('button', { name: 'Отменить' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Не получилось отменить бронь. Проверьте интернет и попробуйте ещё раз.',
    );
  });

  it('explains an unknown order instead of blaming the connection', async () => {
    const api = new MockApi({ latencyMs: 0 });
    renderScreen(<OrderScreen />, { api, at: '/order/o-404', path: '/order/:id' });
    expect(await screen.findByText('Заказ не найден')).toBeInTheDocument();
    expect(screen.queryByText('Нет связи')).toBeNull();
  });
});
