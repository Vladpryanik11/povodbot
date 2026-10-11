import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderScreen } from '../../test/render';
import { OwnerRoutes } from './OwnerRoutes';

const user = userEvent.setup({ delay: null });

const renderAt = (id: string) => renderScreen(<OwnerRoutes />, { at: `/owner/events/${id}`, path: '/owner/*' });

describe('OwnerPreview', () => {
  it('shows unsaved input to the guest and keeps it on return', async () => {
    renderAt('e-own-film');
    const title = await screen.findByLabelText('Название');
    await user.clear(title);
    await user.type(title, 'Новое имя');
    await user.click(screen.getByRole('button', { name: 'Как видит гость' }));
    expect(screen.getByTestId('where')).toHaveTextContent('/owner/events/e-own-film/preview');
    expect(await screen.findByRole('heading', { name: 'Новое имя' })).toBeInTheDocument();
    expect(screen.getByText('Так увидит гость')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Назад' }));
    expect(await screen.findByLabelText('Название')).toHaveValue('Новое имя');
    expect(screen.getByRole('button', { name: 'Сохранить' })).toBeEnabled();
  });

  it('previews a new evening before its first save', async () => {
    renderAt('new');
    await user.type(await screen.findByLabelText('Название'), 'Первый вечер');
    await user.click(screen.getByRole('button', { name: 'Как видит гость' }));
    expect(await screen.findByRole('heading', { name: 'Первый вечер' })).toBeInTheDocument();
    expect(screen.getByTestId('poster-fallback')).toBeInTheDocument();
  });

  it('does not mark a saved evening as changed after a look', async () => {
    renderAt('e-own-film');
    await user.click(await screen.findByRole('button', { name: 'Как видит гость' }));
    await user.click(await screen.findByRole('button', { name: 'Назад' }));
    await screen.findByLabelText('Название');
    expect(screen.getByRole('button', { name: 'Сохранить' })).toBeDisabled();
  });
});
