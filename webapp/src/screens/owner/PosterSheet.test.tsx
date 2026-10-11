import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { MSG } from '../../api/owner/messages';
import { OwnerApiError } from '../../api/owner/OwnerApi';
import type { Poster } from '../../api/types';
import { renderScreen } from '../../test/render';
import { focusFromTap, PosterSheet } from './PosterSheet';

// No timer between keystrokes: the big form re-renders on each one, and a full parallel run is slow enough already.
const user = userEvent.setup({ delay: null });

const photo = () => new File(['x'], 'photo.jpg', { type: 'image/jpeg' });

function renderSheet(poster: Poster | null = null) {
  const onDone = vi.fn();
  const onClose = vi.fn();
  const view = renderScreen(<PosterSheet eventId="e-own-book" poster={poster} onDone={onDone} onClose={onClose} />);
  return { ...view, onDone, onClose };
}

const pick = (file: File) => user.upload(screen.getByLabelText('Фото из галереи'), file);

describe('focusFromTap', () => {
  it('turns a tap into a focus point', () => {
    expect(focusFromTap(130, 240, { left: 100, top: 200, width: 100, height: 100 })).toEqual({ x: 0.3, y: 0.4 });
    expect(focusFromTap(90, 400, { left: 100, top: 200, width: 100, height: 100 })).toEqual({ x: 0, y: 1 });
    expect(focusFromTap(1, 1, { left: 0, top: 0, width: 0, height: 0 })).toBeNull();
  });
});

describe('PosterSheet', () => {
  it('moves all three crop previews to the tapped point', async () => {
    renderSheet();
    await pick(photo());
    const stage = screen.getByLabelText('Точка фокуса');
    stage.getBoundingClientRect = () => ({ left: 0, top: 0, width: 200, height: 250 }) as DOMRect;
    fireEvent.click(stage, { clientX: 60, clientY: 100 });
    for (const name of ['Скоро', 'На этой неделе', 'Билет']) {
      expect(screen.getByRole('figure', { name }).querySelector('img')).toHaveStyle({ objectPosition: '30% 40%' });
    }
  });

  it('uploads the photo with its focus', async () => {
    const { ownerApi, onDone } = renderSheet();
    const upload = vi.spyOn(ownerApi, 'uploadPoster');
    const file = photo();
    await pick(file);
    screen.getByLabelText('Точка фокуса').focus();
    await user.keyboard('{ArrowRight}{ArrowRight}');
    await user.click(screen.getByRole('button', { name: 'Готово' }));
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(upload).toHaveBeenCalledWith('e-own-book', file, { x: 0.6, y: 0.5 });
    expect(onDone.mock.calls[0][0].poster).not.toBeNull();
  });

  it('only moves the focus of the current poster', async () => {
    const { ownerApi, onDone } = renderSheet({ url: './mock/kino.jpg', focusX: 0.5, focusY: 0.4, width: 800, height: 1000 });
    const upload = vi.spyOn(ownerApi, 'uploadPoster');
    const move = vi.spyOn(ownerApi, 'setPosterFocus');
    screen.getByLabelText('Точка фокуса').focus();
    await user.keyboard('{ArrowDown}');
    await user.click(screen.getByRole('button', { name: 'Готово' }));
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(move).toHaveBeenCalledWith('e-own-book', { x: 0.5, y: 0.45 });
    expect(upload).not.toHaveBeenCalled();
  });

  it('closes without a request when nothing changed', async () => {
    const { ownerApi, onClose } = renderSheet({ url: './mock/kino.jpg', focusX: 0.5, focusY: 0.4, width: 800, height: 1000 });
    const move = vi.spyOn(ownerApi, 'setPosterFocus');
    await user.click(screen.getByRole('button', { name: 'Готово' }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(move).not.toHaveBeenCalled();
  });

  it('refuses a file over 15 MB without uploading', async () => {
    const { ownerApi } = renderSheet();
    const upload = vi.spyOn(ownerApi, 'uploadPoster');
    const big = photo();
    Object.defineProperty(big, 'size', { value: 15 * 1024 * 1024 + 1 });
    await pick(big);
    expect(screen.getByText(MSG.photoTooBig)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Готово' }));
    expect(upload).not.toHaveBeenCalled();
  });

  it.each([
    [415, MSG.notAPhoto],
    [422, MSG.photoSmall],
    [429, MSG.uploadBusy],
    [0, MSG.network],
  ])('shows the %s answer in the sheet', async (status, text) => {
    const { ownerApi, onDone } = renderSheet();
    vi.spyOn(ownerApi, 'uploadPoster').mockRejectedValue(new OwnerApiError(status, text, 'poster'));
    await pick(photo());
    await user.click(screen.getByRole('button', { name: 'Готово' }));
    expect(await screen.findByText(text)).toBeInTheDocument();
    expect(onDone).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Готово' })).toBeEnabled();
  });

  it('uploads a photo the browser cannot show at the centre', async () => {
    const { ownerApi, onDone, container } = renderSheet();
    const upload = vi.spyOn(ownerApi, 'uploadPoster');
    const file = photo();
    await pick(file);
    fireEvent.error(screen.getByLabelText('Точка фокуса').querySelector('img')!);
    expect(screen.getByText('Здесь фото не показать — загрузи его, а точку выберешь потом')).toBeInTheDocument();
    expect(screen.queryByRole('figure', { name: 'Скоро' })).not.toBeInTheDocument();
    expect(container.querySelector('img')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Готово' }));
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(upload).toHaveBeenCalledWith('e-own-book', file, { x: 0.5, y: 0.5 });
  });

  it('closes on «Закрыть»', async () => {
    const { onClose } = renderSheet();
    expect(screen.getByRole('dialog', { name: 'Постер' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Закрыть' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
