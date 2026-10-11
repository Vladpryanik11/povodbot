import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { MSG } from '../../api/owner/messages';
import { OwnerApiError } from '../../api/owner/OwnerApi';
import { createTg } from '../../telegram/tg';
import { renderScreen } from '../../test/render';
import { OwnerRoutes } from './OwnerRoutes';

// No timer between keystrokes: the big form re-renders on each one, and a full parallel run is slow enough already.
const user = userEvent.setup({ delay: null });

const renderForm = (id: string) => renderScreen(<OwnerRoutes />, { at: `/owner/events/${id}`, path: '/owner/*' });

const saveButton = () => screen.getByRole('button', { name: 'Сохранить' });

/** Waits until the save went through: nothing is left to save. */
const saved = () => waitFor(() => expect(saveButton()).toBeDisabled());

async function fillNewEvening() {
  await user.type(await screen.findByLabelText('Название'), 'Лекция о джазе');
  await screen.findByRole('option', { name: 'Книжный клуб' });
  await user.selectOptions(screen.getByLabelText('Направление'), 'Книжный клуб');
  fireEvent.change(screen.getByLabelText('Начало'), { target: { value: '2026-10-20T19:00' } });
  fireEvent.change(screen.getByLabelText('Конец'), { target: { value: '2026-10-20T22:00' } });
  await user.type(screen.getByLabelText('Адрес'), 'Покровка, 1');
  await user.type(screen.getByLabelText('Описание'), 'Слушаем пластинки.');
  await user.type(screen.getByLabelText('Вместимость'), '20');
}

async function retitle(text: string) {
  const title = await screen.findByLabelText('Название');
  await user.clear(title);
  if (text) await user.type(title, text);
}

describe('OwnerEventForm', () => {
  it('creates a draft and moves to its address', async () => {
    renderForm('new');
    await fillNewEvening();
    await user.click(saveButton());
    await waitFor(() => expect(screen.getByTestId('where').textContent).toMatch(/^\/owner\/events\/(?!new)/));
    expect(await screen.findByDisplayValue('Лекция о джазе')).toBeInTheDocument();
  });

  it('saves only once on a double tap', async () => {
    const { ownerApi } = renderForm('new');
    const create = vi.spyOn(ownerApi, 'createEvent');
    await fillNewEvening();
    fireEvent.click(saveButton());
    fireEvent.click(saveButton());
    await waitFor(() => expect(screen.getByTestId('where').textContent).not.toBe('/owner/events/new'));
    expect(create).toHaveBeenCalledTimes(1);
  });

  it('shows the server message under its field', async () => {
    renderForm('e-own-book');
    await retitle('');
    await user.click(saveButton());
    expect(await screen.findByText(MSG.title)).toBeInTheDocument();
    expect(screen.getByLabelText('Название')).toHaveAccessibleDescription(MSG.title);
  });

  it('checks prices before sending', async () => {
    const { ownerApi } = renderForm('e-own-book');
    const update = vi.spyOn(ownerApi, 'updateEvent');
    const price = await screen.findByLabelText('Цена билета 1, ₽');
    await user.clear(price);
    await user.type(price, 'дорого');
    await user.click(saveButton());
    expect(await screen.findByText(MSG.ticketPrice)).toBeInTheDocument();
    expect(update).not.toHaveBeenCalled();
  });

  it('does not duplicate a new ticket on the second save', async () => {
    const { ownerApi } = renderForm('e-own-book');
    await user.click(await screen.findByRole('button', { name: 'Добавить билет' }));
    await user.type(screen.getByLabelText('Название билета 2'), 'Студенческий');
    await user.type(screen.getByLabelText('Цена билета 2, ₽'), '500');
    await user.type(screen.getByLabelText('Сколько билетов 2'), '10');
    await user.click(saveButton());
    await saved();
    expect(screen.queryByRole('button', { name: 'Убрать билет 2' })).not.toBeInTheDocument();

    await retitle('Книжный клуб: Сорокин');
    await user.click(saveButton());
    await saved();
    const event = await ownerApi.event('e-own-book');
    expect(event.title).toBe('Книжный клуб: Сорокин');
    expect(event.ticketTypes.filter((t) => t.name === 'Студенческий').length).toBe(1);
  });

  it('keeps the input when the network is gone', async () => {
    const { ownerApi } = renderForm('e-own-book');
    vi.spyOn(ownerApi, 'updateEvent').mockRejectedValue(new OwnerApiError(0, MSG.network));
    await retitle('Книжный клуб: Сорокин');
    await user.click(saveButton());
    expect(await screen.findByText(MSG.network)).toBeInTheDocument();
    expect(screen.getByLabelText('Название')).toHaveValue('Книжный клуб: Сорокин');
    expect(saveButton()).toBeEnabled();
  });

  it('offers the fresh version on a version conflict', async () => {
    const { ownerApi } = renderForm('e-own-book');
    await screen.findByLabelText('Название');
    const { updatedAt } = await ownerApi.event('e-own-book');
    await ownerApi.updateEvent('e-own-book', { updatedAt, title: 'Чужая правка' });
    await retitle('Моя правка');
    await user.click(saveButton());
    expect(await screen.findByText(MSG.conflict)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Загрузить свежую версию' }));
    expect(await screen.findByDisplayValue('Чужая правка')).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();
  });

  it('hides the address when the venue is not decided', async () => {
    const { ownerApi } = renderForm('e-own-book');
    await screen.findByLabelText('Адрес');
    await user.click(screen.getByRole('switch', { name: 'Место уточняется' }));
    expect(screen.queryByLabelText('Адрес')).not.toBeInTheDocument();
    await user.click(saveButton());
    await saved();
    expect((await ownerApi.event('e-own-book')).address).toBeNull();
  });

  it('says what publishing still needs', async () => {
    renderForm('e-own-book');
    expect(await screen.findByRole('button', { name: 'Опубликовать' })).toBeDisabled();
    expect(screen.getByText('Чтобы опубликовать, добавь: фото')).toBeInTheDocument();
    expect(screen.getByText('Черновик · нет фото')).toBeInTheDocument();
  });

  it('saves unsaved input, then publishes', async () => {
    const { ownerApi } = renderForm('e-own-workshop');
    await retitle('Новое название');
    await user.click(screen.getByRole('button', { name: 'Опубликовать' }));
    expect(await screen.findByText(/^Опубликовано · /)).toBeInTheDocument();
    const event = await ownerApi.event('e-own-workshop');
    expect(event.title).toBe('Новое название');
    expect(event.status).toBe('published');
    expect(saveButton()).toBeDisabled();
  });

  it('unpublishes an evening without sales', async () => {
    renderForm('e-own-free');
    await user.click(await screen.findByRole('button', { name: 'Снять с публикации' }));
    expect(await screen.findByText('Черновик')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Опубликовать' })).toBeEnabled();
  });

  it('explains why an evening with sales stays published', async () => {
    renderForm('e-own-film');
    await user.click(await screen.findByRole('button', { name: 'Снять с публикации' }));
    expect(await screen.findByText(MSG.hasOrders)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Загрузить свежую версию' })).not.toBeInTheDocument();
    expect(screen.getByText('Опубликовано · 18/30')).toBeInTheDocument();
  });

  it('keeps unsaved input across a poster upload and saves without a conflict', async () => {
    const { ownerApi } = renderForm('e-own-book');
    await retitle('Без конфликта');
    await user.click(screen.getByRole('button', { name: 'Добавить фото' }));
    expect(screen.queryByRole('button', { name: 'Сохранить' })).not.toBeInTheDocument();
    await user.upload(screen.getByLabelText('Фото из галереи'), new File(['x'], 'photo.jpg', { type: 'image/jpeg' }));
    await user.click(screen.getByRole('button', { name: 'Готово' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(screen.getByLabelText('Название')).toHaveValue('Без конфликта');
    expect(screen.getByRole('button', { name: 'Сменить фото' })).toBeInTheDocument();

    await user.click(saveButton());
    await saved();
    expect(screen.queryByText(MSG.conflict)).not.toBeInTheDocument();
    const event = await ownerApi.event('e-own-book');
    expect(event.title).toBe('Без конфликта');
    expect(event.poster).not.toBeNull();
  });

  it('closes the poster sheet with the Telegram back button', async () => {
    const tg = createTg();
    const back = vi.spyOn(tg.backButton, 'set');
    renderScreen(<OwnerRoutes />, { at: '/owner/events/e-own-book', path: '/owner/*', tg });
    await user.click(await screen.findByRole('button', { name: 'Добавить фото' }));
    const onBack = back.mock.calls.filter((c) => c[0]).at(-1)![0] as () => void;
    act(() => onBack());
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(screen.getByTestId('where')).toHaveTextContent('/owner/events/e-own-book');
  });

  it('disables photos for an unsaved evening', async () => {
    renderForm('new');
    expect(await screen.findByRole('button', { name: 'Добавить фото' })).toBeDisabled();
    expect(screen.getByText('Фото добавишь после первого сохранения')).toBeInTheDocument();
  });

  it('opens a past evening read-only', async () => {
    renderForm('e-own-past');
    expect(await screen.findByText('Вечер прошёл — править нельзя')).toBeInTheDocument();
    expect(screen.getByLabelText('Название')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Сохранить' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Опубликовать' })).not.toBeInTheDocument();
  });
});
