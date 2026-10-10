import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { createTg, type TelegramWebApp } from './tg';
import { TgProvider, useTheme } from './hooks';

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
