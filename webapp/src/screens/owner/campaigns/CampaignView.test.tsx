import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { MockCampaignApi } from '../../../api/campaigns/MockCampaignApi';
import { renderScreen, T0 } from '../../../test/render';
import { CampaignView } from './CampaignView';

async function renderView(id: string) {
  const api = new MockCampaignApi({ latencyMs: 0, now: () => T0 });
  const campaign = await api.campaign(id);
  const view = renderScreen(<CampaignView campaign={campaign} />, {
    campaignApi: api,
    at: `/owner/campaigns/${id}`,
    path: '/owner/campaigns/:id',
  });
  return { ...view, api };
}

const row = (label: string) => screen.getByText(label).parentElement as HTMLElement;

describe('CampaignView', () => {
  it('shows every number of a sent campaign in plain words', async () => {
    await renderView('c-done');
    expect(await screen.findByText('Получатели')).toBeInTheDocument();
    expect(within(row('Получатели')).getByText('214')).toBeInTheDocument();
    expect(within(row('Доставлено')).getByText('205')).toBeInTheDocument();
    expect(within(row('Не доставлено')).getByText('6')).toBeInTheDocument();
    expect(screen.getByText('Заблокировали бота — 3')).toBeInTheDocument();
    expect(screen.getByText('Чат с гостем не найден — 2')).toBeInTheDocument();
    expect(screen.getByText('Отказались от рассылок или заблокировали бота — 1')).toBeInTheDocument();
    expect(within(row('Пропущено из-за лимита')).getByText('3')).toBeInTheDocument();
    expect(within(row('Нажали')).getByText('37')).toBeInTheDocument();
    expect(screen.getByText('и ещё 4 нажатия без входа')).toBeInTheDocument();
    expect(within(row('Купили')).getByText('5')).toBeInTheDocument();
    expect(screen.getByText('Отправлена')).toBeInTheDocument();
  });

  it('stops a running campaign after confirmation', async () => {
    const { api } = await renderView('c-running');
    await userEvent.click(await screen.findByRole('button', { name: 'Остановить' }));
    expect(screen.getByText('Кто ещё не получил — не получит.')).toBeInTheDocument();
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Остановить' }));
    expect(await screen.findByText('Остановлена')).toBeInTheDocument();
    expect((await api.campaign('c-running')).status).toBe('stopped');
  });

  it('repeats a sent campaign as a copy', async () => {
    const { api } = await renderView('c-done');
    await userEvent.click(await screen.findByRole('button', { name: 'Повторить' }));
    await waitFor(() => expect(screen.getByTestId('where').textContent).toMatch(/^\/owner\/campaigns\/c-new-\d+$/));
    const id = screen.getByTestId('where').textContent!.split('/').pop()!;
    expect((await api.campaign(id)).title).toMatch(/\(копия\)$/);
  });

  it('says a cancelled campaign delivered nothing', async () => {
    await renderView('c-cancelled');
    expect(await screen.findByText('Рассылка отменена — никто ничего не получил')).toBeInTheDocument();
    expect(screen.queryByText('Получатели')).not.toBeInTheDocument();
  });
});
