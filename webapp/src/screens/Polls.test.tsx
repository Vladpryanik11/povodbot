import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/AppApi';
import { MockApi } from '../api/mock/MockApi';
import { createTg } from '../telegram/tg';
import { renderScreen, T0 } from '../test/render';
import { EventScreen } from './EventScreen';
import { Polls } from './Polls';

const activeCard = async () => (await screen.findByText('Что смотрим в пятницу?')).closest('section')!;

describe('Polls', () => {
  it('hides results until the vote, then shows them with the change deadline', async () => {
    const api = new MockApi({ latencyMs: 0, now: () => T0 });
    const vote = vi.spyOn(api, 'vote');
    const tg = createTg();
    const selection = vi.spyOn(tg.haptic, 'selection');
    renderScreen(<Polls />, { at: '/polls', api, tg });
    const card = await activeCard();
    expect(within(card).getByText('Проголосовало 24')).toBeInTheDocument();
    expect(within(card).queryByText(/%$/)).toBeNull();

    await userEvent.click(within(card).getByRole('button', { name: /Амели/ }));
    expect(vote).toHaveBeenCalledWith('p-film', 'po-amelie');
    expect(selection).toHaveBeenCalled();
    expect(await within(card).findByText('60%')).toBeInTheDocument();
    expect(within(card).getByText('Ваш голос учтён. Можно передумать до пт, 16 окт, 18:00')).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: /Амели/ })).toHaveAttribute('aria-pressed', 'true');

    await userEvent.click(within(card).getByRole('button', { name: /Ла-Ла Ленд/ }));
    expect(await within(card).findByText('44%')).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: /Ла-Ла Ленд/ })).toHaveAttribute('aria-pressed', 'true');
    expect(within(card).getByRole('button', { name: /Амели/ })).toHaveAttribute('aria-pressed', 'false');
  });

  it('shows the outcome of a closed poll without letting anyone vote', async () => {
    renderScreen(<Polls />, { at: '/polls' });
    const closed = (await screen.findByText('Во что играем в субботу?')).closest('section')!;
    expect(within(closed).getByText('Голосование закрыто')).toBeInTheDocument();
    expect(within(closed).getByText('46%')).toBeInTheDocument();
    expect(within(closed).getByRole('button', { name: /Имаджинариум/ })).toBeDisabled();
  });

  it('explains when the poll closed while the guest was looking', async () => {
    const clock = { t: T0 };
    const api = new MockApi({ latencyMs: 0, now: () => clock.t });
    renderScreen(<Polls />, { at: '/polls', api });
    const card = await activeCard();
    clock.t = Date.parse('2026-10-16T15:00:01Z');
    await userEvent.click(within(card).getByRole('button', { name: /Амели/ }));
    expect(await within(card).findByText('Голосование уже закрыто')).toBeInTheDocument();
  });

  it('says when there is nothing to choose', async () => {
    renderScreen(<Polls />, { at: '/polls', api: new MockApi({ scenario: 'empty', latencyMs: 0, now: () => T0 }) });
    expect(await screen.findByText('Сейчас ничего не выбираем')).toBeInTheDocument();
    expect(screen.getByText('Новое голосование появится — напишем в боте.')).toBeInTheDocument();
  });

  it('lets the guest vote right on the event card', async () => {
    const api = new MockApi({ latencyMs: 0, now: () => T0 });
    const vote = vi.spyOn(api, 'vote');
    renderScreen(<EventScreen />, { at: '/events/e-film', path: '/events/:id', api });
    const card = await activeCard();
    await userEvent.click(within(card).getByRole('button', { name: /Отель «Гранд Будапешт»/ }));
    expect(vote).toHaveBeenCalledWith('p-film', 'po-budapest');
    expect(await within(card).findByText('4%')).toBeInTheDocument();
  });
});

describe('Polls errors', () => {
  it('says when a vote did not go through', async () => {
    const api = new MockApi({ latencyMs: 0, now: () => T0 });
    vi.spyOn(api, 'vote').mockRejectedValue(new ApiError('network'));
    renderScreen(<Polls />, { at: '/polls', api });
    const card = await activeCard();
    await userEvent.click(within(card).getByRole('button', { name: /Амели/ }));
    expect(await within(card).findByText('Не получилось проголосовать. Попробуйте ещё раз.')).toBeInTheDocument();
  });
});
