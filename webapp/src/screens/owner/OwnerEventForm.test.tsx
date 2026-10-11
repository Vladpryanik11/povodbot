import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { MSG } from '../../api/owner/messages';
import { OwnerApiError } from '../../api/owner/OwnerApi';
import { renderScreen } from '../../test/render';
import { OwnerRoutes } from './OwnerRoutes';

const renderForm = (id: string) => renderScreen(<OwnerRoutes />, { at: `/owner/events/${id}`, path: '/owner/*' });

const saveButton = () => screen.getByRole('button', { name: 'Сохранить' });

/** Waits until the save went through: nothing is left to save. */
const saved = () => waitFor(() => expect(saveButton()).toBeDisabled());

async function fillNewEvening() {
  await userEvent.type(await screen.findByLabelText('Название'), 'Лекция о джазе');
  await screen.findByRole('option', { name: 'Книжный клуб' });
  await userEvent.selectOptions(screen.getByLabelText('Направление'), 'Книжный клуб');
  fireEvent.change(screen.getByLabelText('Начало'), { target: { value: '2026-10-20T19:00' } });
  fireEvent.change(screen.getByLabelText('Конец'), { target: { value: '2026-10-20T22:00' } });
  await userEvent.type(screen.getByLabelText('Адрес'), 'Покровка, 1');
  await userEvent.type(screen.getByLabelText('Описание'), 'Слушаем пластинки.');
  await userEvent.type(screen.getByLabelText('Вместимость'), '20');
}

async function retitle(text: string) {
  const title = await screen.findByLabelText('Название');
  await userEvent.clear(title);
  if (text) await userEvent.type(title, text);
}

describe('OwnerEventForm', () => {
  it('creates a draft and moves to its address', async () => {
    renderForm('new');
    await fillNewEvening();
    await userEvent.click(saveButton());
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
    await userEvent.click(saveButton());
    expect(await screen.findByText(MSG.title)).toBeInTheDocument();
    expect(screen.getByLabelText('Название')).toHaveAccessibleDescription(MSG.title);
  });

  it('checks prices before sending', async () => {
    const { ownerApi } = renderForm('e-own-book');
    const update = vi.spyOn(ownerApi, 'updateEvent');
    const price = await screen.findByLabelText('Цена билета 1, ₽');
    await userEvent.clear(price);
    await userEvent.type(price, 'дорого');
    await userEvent.click(saveButton());
    expect(await screen.findByText(MSG.ticketPrice)).toBeInTheDocument();
    expect(update).not.toHaveBeenCalled();
  });

  it('does not duplicate a new ticket on the second save', async () => {
    const { ownerApi } = renderForm('e-own-book');
    await userEvent.click(await screen.findByRole('button', { name: 'Добавить билет' }));
    await userEvent.type(screen.getByLabelText('Название билета 2'), 'Студенческий');
    await userEvent.type(screen.getByLabelText('Цена билета 2, ₽'), '500');
    await userEvent.type(screen.getByLabelText('Сколько билетов 2'), '10');
    await userEvent.click(saveButton());
    await saved();
    expect(screen.queryByRole('button', { name: 'Убрать билет 2' })).not.toBeInTheDocument();

    await retitle('Книжный клуб: Сорокин');
    await userEvent.click(saveButton());
    await saved();
    const event = await ownerApi.event('e-own-book');
    expect(event.title).toBe('Книжный клуб: Сорокин');
    expect(event.ticketTypes.filter((t) => t.name === 'Студенческий').length).toBe(1);
  });

  it('keeps the input when the network is gone', async () => {
    const { ownerApi } = renderForm('e-own-book');
    vi.spyOn(ownerApi, 'updateEvent').mockRejectedValue(new OwnerApiError(0, MSG.network));
    await retitle('Книжный клуб: Сорокин');
    await userEvent.click(saveButton());
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
    await userEvent.click(saveButton());
    expect(await screen.findByText(MSG.conflict)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Загрузить свежую версию' }));
    expect(await screen.findByDisplayValue('Чужая правка')).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();
  });

  it('hides the address when the venue is not decided', async () => {
    const { ownerApi } = renderForm('e-own-book');
    await screen.findByLabelText('Адрес');
    await userEvent.click(screen.getByRole('switch', { name: 'Место уточняется' }));
    expect(screen.queryByLabelText('Адрес')).not.toBeInTheDocument();
    await userEvent.click(saveButton());
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
    await userEvent.click(screen.getByRole('button', { name: 'Опубликовать' }));
    expect(await screen.findByText(/^Опубликовано · /)).toBeInTheDocument();
    const event = await ownerApi.event('e-own-workshop');
    expect(event.title).toBe('Новое название');
    expect(event.status).toBe('published');
    expect(saveButton()).toBeDisabled();
  });

  it('unpublishes an evening without sales', async () => {
    renderForm('e-own-free');
    await userEvent.click(await screen.findByRole('button', { name: 'Снять с публикации' }));
    expect(await screen.findByText('Черновик')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Опубликовать' })).toBeEnabled();
  });

  it('explains why an evening with sales stays published', async () => {
    renderForm('e-own-film');
    await userEvent.click(await screen.findByRole('button', { name: 'Снять с публикации' }));
    expect(await screen.findByText(MSG.hasOrders)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Загрузить свежую версию' })).not.toBeInTheDocument();
    expect(screen.getByText('Опубликовано · 18/30')).toBeInTheDocument();
  });

  it('opens a past evening read-only', async () => {
    renderForm('e-own-past');
    expect(await screen.findByText('Вечер прошёл — править нельзя')).toBeInTheDocument();
    expect(screen.getByLabelText('Название')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Сохранить' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Опубликовать' })).not.toBeInTheDocument();
  });
});
