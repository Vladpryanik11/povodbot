import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { CMSG } from '../../../api/campaigns/messages';
import { MockCampaignApi } from '../../../api/campaigns/MockCampaignApi';
import { renderScreen, T0 } from '../../../test/render';
import { CampaignRoutes } from './CampaignRoutes';

function renderEditor(at: string, options: { telegramLinked?: boolean } = {}) {
  const campaignApi = new MockCampaignApi({ latencyMs: 0, now: () => T0, ...options });
  const view = renderScreen(<CampaignRoutes />, { campaignApi, at, path: '/owner/campaigns/*' });
  return { ...view, campaignApi };
}

const sendButton = () => screen.getByRole('button', { name: 'Отправить…' });
const eventSelect = async () => (await screen.findAllByLabelText('Вечер'))[0] as HTMLSelectElement;
const where = () => screen.getByTestId('where').textContent;

describe('CampaignEditor', () => {
  it('fills a template once an evening is picked', async () => {
    renderEditor('/owner/campaigns/new?template=tb-new');
    expect(await screen.findByText('Выбери вечер — {event} и {date} заменятся сами')).toBeInTheDocument();
    expect(sendButton()).toBeDisabled();

    await userEvent.selectOptions(await eventSelect(), 'Кино на крыше: «Амели»');
    expect((screen.getByLabelText('Текст') as HTMLTextAreaElement).value).toMatch(/у нас «Кино на крыше: «Амели»»/);
    expect(screen.getByRole('radio', { name: 'Афиша вечера' })).toBeChecked();
    expect(within(screen.getByRole('figure', { name: 'Предпросмотр' })).getByText('Открыть вечер')).toBeInTheDocument();
    expect(screen.queryByText('Выбери вечер — {event} и {date} заменятся сами')).not.toBeInTheDocument();
  });

  it('escapes <, > and & and opens the saved campaign', async () => {
    const { campaignApi } = renderEditor('/owner/campaigns/new');
    const create = vi.spyOn(campaignApi, 'createCampaign');
    await userEvent.type(await screen.findByLabelText('Текст'), 'a < b & c');
    await userEvent.click(screen.getByRole('button', { name: 'Сохранить черновик' }));
    await waitFor(() => expect(where()).toMatch(/^\/owner\/campaigns\/c-new-\d+$/));
    expect(create.mock.calls[0][0].body).toBe('a &lt; b &amp; c');
  });

  it('says so when the campaign changed elsewhere', async () => {
    const { campaignApi } = renderEditor('/owner/campaigns/c-draft');
    const title = await screen.findByLabelText('Название');
    const fresh = await campaignApi.campaign('c-draft');
    await campaignApi.updateCampaign('c-draft', { title: 'Из другой вкладки', updatedAt: fresh.updatedAt });
    await userEvent.type(title, '!');
    await userEvent.click(screen.getByRole('button', { name: 'Сохранить черновик' }));
    expect(await screen.findByText(CMSG.stale)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Загрузить свежую версию' })).toBeInTheDocument();
  });

  it('tells the owner when the bot cannot write to them', async () => {
    renderEditor('/owner/campaigns/c-draft', { telegramLinked: false });
    await userEvent.click(await screen.findByRole('button', { name: 'Отправить себе' }));
    expect(await screen.findByText(CMSG.botBlocked)).toBeInTheDocument();
  });

  it('cancels a scheduled campaign', async () => {
    renderEditor('/owner/campaigns/c-scheduled');
    await userEvent.click(await screen.findByRole('button', { name: 'Отменить рассылку' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Отменить рассылку' }));
    expect(await screen.findByText('Отменена')).toBeInTheDocument();
  });

  it('does not send to nobody', async () => {
    renderEditor('/owner/campaigns/c-draft');
    await screen.findByLabelText('Название');
    const audienceEvent = screen.getByLabelText('Вечер', { selector: '#audience-event' });
    await waitFor(() => expect(within(audienceEvent).getAllByRole('option').map((o) => o.getAttribute('value'))).toContain('e-own-free'));
    await userEvent.selectOptions(audienceEvent, 'e-own-free');
    await userEvent.selectOptions(screen.getByLabelText('Кто'), 'going');
    expect(await screen.findByText('Получат 0')).toBeInTheDocument();
    expect(sendButton()).toBeDisabled();
  });

  it('opens the send sheet right after saving a new campaign', async () => {
    renderEditor('/owner/campaigns/new');
    await userEvent.type(await screen.findByLabelText('Текст'), 'Привет');
    await waitFor(() => expect(sendButton()).toBeEnabled());
    await userEvent.click(sendButton());
    expect(await screen.findByRole('dialog', { name: 'Отправка' })).toBeInTheDocument();
  });
});
