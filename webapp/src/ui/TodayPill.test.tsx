import { act, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MockApi } from '../api/mock/MockApi';
import { renderScreen, T0 } from '../test/render';
import { TodayPill } from './TodayPill';

/** Waits until the pill's queries have answered, so a missing pill is a decision, not a pending fetch. */
async function settled(api: MockApi, render: () => void) {
  const me = vi.spyOn(api, 'me');
  const tickets = vi.spyOn(api, 'tickets');
  render();
  await vi.waitFor(() => {
    expect(me).toHaveBeenCalled();
    expect(tickets).toHaveBeenCalled();
  });
  await Promise.all([me.mock.results[0].value, tickets.mock.results[0].value]);
  await act(async () => {});
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(T0);
  localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('TodayPill', () => {
  it('shows tonight’s ticket above the menu and opens it', async () => {
    renderScreen(<TodayPill />, { at: '/favorites' });
    const pill = await screen.findByRole('link', { name: /Сегодня · 23:00/ });
    expect(pill).toHaveAttribute('href', '/tickets/tk-1');
    expect(pill).toHaveTextContent('Амели на большом экране');
  });

  it('is hidden off the tab screens, e.g. on the event screen', async () => {
    const api = new MockApi({ latencyMs: 0, now: () => T0 });
    await settled(api, () => renderScreen(<TodayPill />, { api, at: '/events/e-film' }));
    expect(screen.queryByRole('link', { name: /Сегодня/ })).toBeNull();
  });

  it('gives its place on Home to the reservation plaque', async () => {
    const api = new MockApi({ latencyMs: 0, now: () => T0 });
    const detail = await api.event('e-workshop');
    await api.createOrder('e-workshop', [{ ticketTypeId: detail.ticketTypes[0].id, qty: 1 }]);
    await settled(api, () => renderScreen(<TodayPill />, { api, at: '/' }));
    expect(screen.queryByRole('link', { name: /Сегодня/ })).toBeNull();
  });
});
