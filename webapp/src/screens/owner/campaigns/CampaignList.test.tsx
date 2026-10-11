import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { MockCampaignApi } from '../../../api/campaigns/MockCampaignApi';
import { MSG } from '../../../api/owner/messages';
import { renderScreen, T0 } from '../../../test/render';
import { OwnerRoutes } from '../OwnerRoutes';

const renderList = (options: Parameters<typeof renderScreen>[1] = {}) =>
  renderScreen(<OwnerRoutes />, { at: '/owner/campaigns', path: '/owner/*', ...options });

describe('CampaignList', () => {
  it('opens on drafts', async () => {
    renderList();
    expect(await screen.findByText('Анонс «Амели»')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Черновики' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.queryByText('Спасибо за «Сталкера»')).not.toBeInTheDocument();
    expect(screen.getAllByRole('link').map((a) => a.getAttribute('href'))).toContain('/owner/campaigns/c-draft');
  });

  it('shows how sent ones went', async () => {
    renderList();
    await userEvent.click(await screen.findByRole('radio', { name: 'Отправлены' }));
    expect(await screen.findByText('доставлено 205 · нажали 37')).toBeInTheDocument();
    expect(screen.getAllByText('214 гостей').length).toBeGreaterThan(0);
    expect(screen.getByText('Отменена · вечер снят с публикации')).toBeInTheDocument();
  });

  it('says when nothing is scheduled', async () => {
    const api = new MockCampaignApi({ latencyMs: 0, now: () => T0 });
    await api.cancel('c-scheduled');
    renderList({ campaignApi: api });
    await userEvent.click(await screen.findByRole('radio', { name: 'Запланированы' }));
    expect(await screen.findByText('Запланированных нет')).toBeInTheDocument();
  });

  it('starts a new campaign from the bottom bar', async () => {
    renderList();
    await userEvent.click(await screen.findByRole('button', { name: /Новая рассылка/ }));
    expect(screen.getByTestId('where')).toHaveTextContent('/owner/campaigns/start');
  });

  it('turns away the door staff', async () => {
    renderList({ campaignApi: new MockCampaignApi({ role: 'entrance', latencyMs: 0, now: () => T0 }) });
    expect(await screen.findByText('Нет доступа')).toBeInTheDocument();
    expect(screen.getByText(MSG.noAccess)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Новая рассылка/ })).not.toBeInTheDocument();
  });

  it('opens evenings where broadcasts are not available', async () => {
    renderList({ campaignApi: null });
    expect(await screen.findByRole('heading', { name: 'Мои вечера' })).toBeInTheDocument();
  });
});
