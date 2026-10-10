import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { MockApi } from '../api/mock/MockApi';
import { renderScreen, T0 } from '../test/render';
import { MockPay } from './MockPay';

describe('MockPay', () => {
  it('pays the order and returns to its status screen', async () => {
    const api = new MockApi({ latencyMs: 0, now: () => T0 });
    const detail = await api.event('e-film');
    const order = await api.createOrder('e-film', [{ ticketTypeId: detail.ticketTypes[0].id, qty: 2 }]);
    const complete = vi.spyOn(api, 'completePayment');
    renderScreen(<MockPay />, { api, at: `/mock-pay/${order.id}`, path: '/mock-pay/:id' });
    expect(await screen.findByText('3 100 ₽')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Оплатить' }));
    expect(complete).toHaveBeenCalledWith(order.id, 'paid');
    expect(await screen.findByText(`/order/${order.id}`, { selector: 'output' })).toBeInTheDocument();
  });
});
