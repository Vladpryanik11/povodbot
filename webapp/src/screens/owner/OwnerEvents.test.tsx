import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { MSG } from '../../api/owner/messages';
import { MockOwnerApi } from '../../api/owner/MockOwnerApi';
import { buildOwnerFixtures, LEGACY_POSTER_URL } from '../../api/owner/ownerFixtures';
import { renderScreen, T0 } from '../../test/render';
import { OwnerRoutes } from './OwnerRoutes';

const renderList = (options: Parameters<typeof renderScreen>[1] = {}) =>
  renderScreen(<OwnerRoutes />, { at: '/owner', path: '/owner/*', ...options });

describe('OwnerEvents', () => {
  it('lists live evenings with status pills', async () => {
    renderList();
    expect(await screen.findByText('Опубликовано · 18/30')).toBeInTheDocument();
    expect(screen.getByText('Черновик · нет фото')).toBeInTheDocument();
    expect(screen.getAllByRole('link').map((a) => a.getAttribute('href'))).toContain('/owner/events/e-own-film');
    expect(screen.getAllByTestId('thumb-empty').length).toBe(1);
  });

  it('filters drafts and past evenings', async () => {
    renderList();
    await userEvent.click(await screen.findByRole('radio', { name: 'Прошли' }));
    expect(await screen.findByText('Прошёл · 25/30')).toBeInTheDocument();
    expect(screen.queryByText('Опубликовано · 18/30')).not.toBeInTheDocument();
    expect(screen.getByRole('radiogroup', { name: 'Фильтр вечеров' })).toBeInTheDocument();
  });

  it('shows a legacy poster without its size', async () => {
    const { container } = renderList();
    await screen.findByText('Опубликовано · 18/30');
    // alt="" keeps it out of the accessibility tree, so it is found by src.
    expect(container.querySelector(`img[src="${LEGACY_POSTER_URL}"]`)).not.toBeNull();
  });

  it('starts a new evening from the bottom bar', async () => {
    renderList();
    await userEvent.click(await screen.findByRole('button', { name: /Новый вечер/ }));
    expect(screen.getByTestId('where')).toHaveTextContent('/owner/events/new');
  });

  it('says when there are no drafts', async () => {
    const fixtures = buildOwnerFixtures(T0);
    fixtures.events = fixtures.events.filter((e) => e.status !== 'draft');
    renderList({ ownerApi: new MockOwnerApi({ latencyMs: 0, now: () => T0, fixtures }) });
    await userEvent.click(await screen.findByRole('radio', { name: 'Черновики' }));
    expect(await screen.findByText('Черновиков нет')).toBeInTheDocument();
  });

  it('turns a guest away', async () => {
    renderList({ ownerApi: new MockOwnerApi({ role: 'guest', latencyMs: 0 }) });
    expect(await screen.findByText(MSG.noAccess)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Новый вечер/ })).not.toBeInTheDocument();
  });

  it('offers a retry when the list does not load', async () => {
    renderList({ ownerApi: new MockOwnerApi({ offline: true, latencyMs: 0 }) });
    expect(await screen.findByRole('button', { name: 'Повторить' })).toBeInTheDocument();
    expect(screen.getByText(MSG.network)).toBeInTheDocument();
  });
});
