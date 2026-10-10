import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { createTg, mainButtonStore, type TelegramWebApp } from './tg';
import { TgProvider, useMainButton, useTheme } from './hooks';

function ThemeProbe() {
  const theme = useTheme();
  return <span data-testid="theme">{theme}</span>;
}

describe('useTheme', () => {
  it('forces dark theme even when Telegram is light', () => {
    const web = {
      colorScheme: 'light',
      initDataUnsafe: {},
      onEvent: vi.fn(),
      offEvent: vi.fn(),
      setHeaderColor: vi.fn(),
      setBackgroundColor: vi.fn(),
    } as unknown as TelegramWebApp;
    const tg = createTg(web);

    const view = render(
      <TgProvider value={tg}>
        <ThemeProbe />
      </TgProvider>,
    );
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(view.getByTestId('theme').textContent).toBe('dark');
    expect(web.setHeaderColor).toHaveBeenCalledWith('#000000');
    expect(web.setBackgroundColor).toHaveBeenCalledWith('#000000');
    expect(web.onEvent).not.toHaveBeenCalledWith('themeChanged', expect.anything());
  });
});

function MainProbe({ onClick }: { onClick: () => void }) {
  useMainButton({ text: 'Купить', enabled: true, progress: false, summary: 'от 1 500 ₽', onClick });
  return null;
}

describe('useMainButton', () => {
  it('writes only to the store, never to the Telegram MainButton, and passes summary through', () => {
    const tg = createTg();
    const set = vi.spyOn(tg.mainButton, 'set');
    const onClick = vi.fn();
    const view = render(
      <TgProvider value={tg}>
        <MainProbe onClick={onClick} />
      </TgProvider>,
    );
    expect(set).not.toHaveBeenCalled();
    expect(mainButtonStore.get()).toMatchObject({ text: 'Купить', enabled: true, progress: false, summary: 'от 1 500 ₽' });
    mainButtonStore.get()!.onClick();
    expect(onClick).toHaveBeenCalledTimes(1);
    view.unmount();
    expect(mainButtonStore.get()).toBeNull();
    expect(set).not.toHaveBeenCalled();
  });
});
