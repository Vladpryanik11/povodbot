import { act, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { createTg, type TelegramWebApp } from './tg';
import { TgProvider, useTheme } from './hooks';

function ThemeProbe() {
  const theme = useTheme();
  return <span data-testid="theme">{theme}</span>;
}

describe('useTheme', () => {
  it('applies the telegram color scheme and follows themeChanged', () => {
    let listener: (() => void) | undefined;
    const web = {
      colorScheme: 'dark',
      initDataUnsafe: {},
      onEvent: vi.fn((name: string, cb: () => void) => {
        if (name === 'themeChanged') listener = cb;
      }),
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
    expect(web.setHeaderColor).toHaveBeenCalledWith('#0F0E12');

    act(() => {
      (web as { colorScheme: string }).colorScheme = 'light';
      listener?.();
    });
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(view.getByTestId('theme').textContent).toBe('light');
    expect(web.setHeaderColor).toHaveBeenLastCalledWith('#F6F3EE');
  });
});
