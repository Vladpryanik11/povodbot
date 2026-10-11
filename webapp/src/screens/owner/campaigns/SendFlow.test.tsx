import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { CMSG } from '../../../api/campaigns/messages';
import { MockCampaignApi } from '../../../api/campaigns/MockCampaignApi';
import { renderScreen, T0 } from '../../../test/render';
import { CampaignRoutes } from './CampaignRoutes';

function renderDraft(id: string, now = T0) {
  const campaignApi = new MockCampaignApi({ latencyMs: 0, now: () => now });
  const view = renderScreen(<CampaignRoutes />, { campaignApi, at: `/owner/campaigns/${id}`, path: '/owner/campaigns/*' });
  return { ...view, campaignApi };
}

async function openSheet() {
  const send = await screen.findByRole('button', { name: 'Отправить…' });
  await waitFor(() => expect(send).toBeEnabled());
  await userEvent.click(send);
  return screen.findByRole('dialog', { name: 'Отправка' });
}

describe('SendFlow', () => {
  it('sends once however fast the owner taps', async () => {
    const { campaignApi } = renderDraft('c-draft');
    const send = vi.spyOn(campaignApi, 'send');
    await userEvent.click(within(await openSheet()).getByRole('button', { name: 'Дальше' }));
    expect(screen.getByText('Отправить 37 гостям?')).toBeInTheDocument();
    const confirm = screen.getByRole('button', { name: 'Отправить' });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(await screen.findByText('Идёт отправка')).toBeInTheDocument();
    expect(send).toHaveBeenCalledTimes(1);
  });

  it('offers the morning at night', async () => {
    const night = Date.parse('2026-10-10T20:00:00Z');
    const { campaignApi } = renderDraft('c-draft', night);
    await userEvent.click(within(await openSheet()).getByRole('button', { name: 'Дальше' }));
    await userEvent.click(screen.getByRole('button', { name: 'Отправить' }));
    expect(await screen.findByText(CMSG.night)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Да' }));
    await waitFor(async () => expect((await campaignApi.campaign('c-draft')).scheduledAt).toBe('2026-10-11T07:00:00.000Z'));
  });

  it('leaves a draft when the owner says no to the morning', async () => {
    const { campaignApi } = renderDraft('c-draft', Date.parse('2026-10-10T20:00:00Z'));
    await userEvent.click(within(await openSheet()).getByRole('button', { name: 'Дальше' }));
    await userEvent.click(screen.getByRole('button', { name: 'Отправить' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Нет' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect((await campaignApi.campaign('c-draft')).status).toBe('draft');
  });

  it('puts a night time under the time field', async () => {
    renderDraft('c-draft');
    const sheet = await openSheet();
    await userEvent.click(within(sheet).getByRole('radio', { name: 'Запланировать' }));
    const time = within(sheet).getByLabelText('Время, МСК');
    fireEvent.change(time, { target: { value: '22:30' } });
    await userEvent.click(within(sheet).getByRole('button', { name: 'Дальше' }));
    await userEvent.click(screen.getByRole('button', { name: 'Запланировать' }));
    expect(await screen.findByText(CMSG.quietAt)).toBeInTheDocument();
    expect(screen.getByLabelText('Время, МСК')).toHaveAttribute('aria-invalid', 'true');
  });

  it('shows an unpublished evening under «Вечер»', async () => {
    renderDraft('c-gone');
    await userEvent.click(within(await openSheet()).getByRole('button', { name: 'Дальше' }));
    await userEvent.click(screen.getByRole('button', { name: /^Отправить$/ }));
    expect(await screen.findByText(CMSG.eventGone)).toBeInTheDocument();
  });
});
