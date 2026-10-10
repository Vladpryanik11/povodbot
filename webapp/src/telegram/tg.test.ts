import { describe, expect, it, vi } from 'vitest';
import { createTg, mainButtonStore, type TelegramWebApp } from './tg';

function fakeWebApp(overrides: Partial<TelegramWebApp> = {}): TelegramWebApp {
  const handlers: Array<() => void> = [];
  return {
    colorScheme: 'dark',
    initDataUnsafe: { start_param: 'event_e1' },
    ready: vi.fn(),
    expand: vi.fn(),
    disableVerticalSwipes: vi.fn(),
    onEvent: vi.fn(),
    offEvent: vi.fn(),
    openLink: vi.fn(),
    openTelegramLink: vi.fn(),
    enableClosingConfirmation: vi.fn(),
    disableClosingConfirmation: vi.fn(),
    setHeaderColor: vi.fn(),
    setBackgroundColor: vi.fn(),
    HapticFeedback: {
      impactOccurred: vi.fn(),
      selectionChanged: vi.fn(),
      notificationOccurred: vi.fn(),
    },
    MainButton: {
      setText: vi.fn(),
      enable: vi.fn(),
      disable: vi.fn(),
      show: vi.fn(),
      hide: vi.fn(),
      showProgress: vi.fn(),
      hideProgress: vi.fn(),
      onClick: vi.fn((cb: () => void) => handlers.push(cb)),
      offClick: vi.fn((cb: () => void) => {
        const i = handlers.indexOf(cb);
        if (i >= 0) handlers.splice(i, 1);
      }),
    },
    BackButton: { show: vi.fn(), hide: vi.fn(), onClick: vi.fn(), offClick: vi.fn() },
    ...overrides,
    // exposed for assertions
    __mainHandlers: handlers,
  } as unknown as TelegramWebApp;
}

describe('createTg without Telegram (browser stub)', () => {
  it('is not telegram and stores values in localStorage', async () => {
    const tg = createTg();
    expect(tg.isTelegram).toBe(false);
    await tg.storage.set('k', 'v');
    expect(await tg.storage.get('k')).toBe('v');
  });

  it('writes main button state into the in-page store', () => {
    const tg = createTg();
    const onClick = vi.fn();
    tg.mainButton.set({ text: 'Оплатить 3 100 ₽', enabled: true, progress: false, onClick });
    expect(mainButtonStore.get()?.text).toBe('Оплатить 3 100 ₽');
    tg.mainButton.set(null);
    expect(mainButtonStore.get()).toBeNull();
  });
});

describe('createTg with Telegram WebApp', () => {
  it('forwards lifecycle calls and reads start_param', () => {
    const web = fakeWebApp();
    const tg = createTg(web);
    tg.ready();
    tg.expand();
    tg.disableVerticalSwipes();
    expect(tg.isTelegram).toBe(true);
    expect(web.ready).toHaveBeenCalled();
    expect(web.expand).toHaveBeenCalled();
    expect(web.disableVerticalSwipes).toHaveBeenCalled();
    expect(tg.startParam).toBe('event_e1');
    expect(tg.colorScheme).toBe('dark');
  });

  it('shows the native main button and never stacks click handlers', () => {
    const web = fakeWebApp();
    const tg = createTg(web);
    const first = vi.fn();
    const second = vi.fn();
    tg.mainButton.set({ text: 'Оплатить 3 100 ₽', enabled: true, progress: false, onClick: first });
    expect(web.MainButton!.setText).toHaveBeenCalledWith('Оплатить 3 100 ₽');
    expect(web.MainButton!.enable).toHaveBeenCalled();
    expect(web.MainButton!.show).toHaveBeenCalled();
    tg.mainButton.set({ text: 'Оплатить 4 650 ₽', enabled: true, progress: false, onClick: second });
    const handlers = (web as unknown as { __mainHandlers: Array<() => void> }).__mainHandlers;
    expect(handlers).toHaveLength(1);
    handlers[0]();
    expect(second).toHaveBeenCalledTimes(1);
    expect(first).not.toHaveBeenCalled();
    tg.mainButton.set(null);
    expect(web.MainButton!.hide).toHaveBeenCalled();
    expect(handlers).toHaveLength(0);
  });

  it('falls back to the in-page store on old clients without MainButton', () => {
    const web = fakeWebApp({ MainButton: undefined });
    const tg = createTg(web);
    tg.mainButton.set({ text: 'Выберите билеты', enabled: false, progress: false, onClick: vi.fn() });
    expect(mainButtonStore.get()?.text).toBe('Выберите билеты');
    tg.mainButton.set(null);
  });

  it('sets chrome colors only when the client supports them', () => {
    const web = fakeWebApp();
    createTg(web).setChromeColor('#0F0E12');
    expect(web.setHeaderColor).toHaveBeenCalledWith('#0F0E12');
    expect(web.setBackgroundColor).toHaveBeenCalledWith('#0F0E12');
    const old = fakeWebApp({ setHeaderColor: undefined, setBackgroundColor: undefined });
    expect(() => createTg(old).setChromeColor('#0F0E12')).not.toThrow();
  });
});

describe('main button colours', () => {
  it('paints the native main button in the club accent and mutes it when disabled', () => {
    const web = fakeWebApp();
    const setParams = vi.fn();
    (web.MainButton as unknown as { setParams: typeof setParams }).setParams = setParams;
    const tg = createTg(web);
    tg.mainButton.set({ text: 'Оплатить 1 550 ₽', enabled: true, progress: false, onClick: vi.fn() });
    expect(setParams).toHaveBeenLastCalledWith({ color: '#FF7A3D', text_color: '#2B1205' });
    tg.mainButton.set({ text: 'Выберите билеты', enabled: false, progress: false, onClick: vi.fn() });
    expect(setParams).toHaveBeenLastCalledWith({ color: '#2A262F', text_color: '#BDB6AE' });
    tg.mainButton.set(null);
  });
});

describe('tg.user', () => {
  it('takes the first name and photo from initDataUnsafe.user', () => {
    const web = { colorScheme: 'dark', initDataUnsafe: { user: { first_name: 'Аня', photo_url: 'https://t.me/i/a.jpg' } } } as unknown as TelegramWebApp;
    expect(createTg(web).user).toEqual({ firstName: 'Аня', photoUrl: 'https://t.me/i/a.jpg' });
    const noPhoto = { colorScheme: 'dark', initDataUnsafe: { user: { first_name: 'Аня' } } } as unknown as TelegramWebApp;
    expect(createTg(noPhoto).user).toEqual({ firstName: 'Аня', photoUrl: null });
  });

  it('is null outside Telegram or without a user', () => {
    expect(createTg().user).toBeNull();
    expect(createTg({ colorScheme: 'dark', initDataUnsafe: {} } as TelegramWebApp).user).toBeNull();
  });
});
