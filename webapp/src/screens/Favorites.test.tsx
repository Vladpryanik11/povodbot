import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { createTg } from '../telegram/tg';
import { renderScreen } from '../test/render';
import { Favorites } from './Favorites';

beforeEach(() => localStorage.clear());

describe('Favorites', () => {
  it('invites to tap the heart when nothing is saved', async () => {
    renderScreen(<Favorites />, { at: '/favorites' });
    expect(await screen.findByText('Тут будут сохранённые вечера')).toBeInTheDocument();
    expect(screen.getByText('Жми сердечко на афише — соберём всё здесь.')).toBeInTheDocument();
  });

  it('shows the saved evenings from CloudStorage', async () => {
    const tg = createTg();
    await tg.storage.set('fav', '["e-workshop"]');
    renderScreen(<Favorites />, { at: '/favorites', tg });
    expect(await screen.findByText('Лепим чашку из глины')).toBeInTheDocument();
    expect(screen.queryByText('Амели на большом экране')).toBeNull();
  });
});
