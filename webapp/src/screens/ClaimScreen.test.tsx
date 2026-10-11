import { screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { buildFixtures } from '../api/mock/fixtures';
import { MockApi } from '../api/mock/MockApi';
import { renderScreen, T0 } from '../test/render';
import { ClaimScreen } from './ClaimScreen';

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

describe('Claim screen', () => {
  it('gives the ticket to the friend once and explains a second attempt', async () => {
    const api = withPair();
    const { shareUrl } = await api.shareTicket('tk-2');
    const token = new URL(shareUrl).searchParams.get('startapp')!.replace('claim_', '');
    const first = renderScreen(<ClaimScreen />, { api, at: `/claim/${token}`, path: '/claim/:token' });
    expect(await screen.findByText('Билет твой')).toBeInTheDocument();
    first.unmount();
    renderScreen(<ClaimScreen />, { api, at: `/claim/${token}`, path: '/claim/:token' });
    expect(await screen.findByText('Этот билет уже забрал другой гость')).toBeInTheDocument();
  });
});
