export type ColorScheme = 'light' | 'dark';

export interface MainButtonState {
  text: string;
  enabled: boolean;
  progress: boolean;
  /** Left side of the page bottom bar: «2 билета · 3 100 ₽», «от 1 500 ₽». */
  summary?: string;
  onClick: () => void;
}

type Callback = () => void;

/** The subset of window.Telegram.WebApp this app uses. Every member is optional on old clients. */
export interface TelegramWebApp {
  colorScheme: ColorScheme;
  platform?: string;
  initData?: string;
  initDataUnsafe: { start_param?: string; user?: { first_name: string; photo_url?: string } };
  ready?: () => void;
  expand?: () => void;
  disableVerticalSwipes?: () => void;
  onEvent?: (name: string, cb: Callback) => void;
  offEvent?: (name: string, cb: Callback) => void;
  openLink?: (url: string) => void;
  openTelegramLink?: (url: string) => void;
  enableClosingConfirmation?: () => void;
  disableClosingConfirmation?: () => void;
  setHeaderColor?: (color: string) => void;
  setBackgroundColor?: (color: string) => void;
  setBottomBarColor?: (color: string) => void;
  HapticFeedback?: {
    impactOccurred: (style: 'light' | 'medium') => void;
    selectionChanged: () => void;
    notificationOccurred: (type: 'success' | 'warning' | 'error') => void;
  };
  MainButton?: {
    setText: (text: string) => void;
    enable: () => void;
    disable: () => void;
    show: () => void;
    hide: () => void;
    showProgress: (leaveActive?: boolean) => void;
    hideProgress: () => void;
    onClick: (cb: Callback) => void;
    offClick: (cb: Callback) => void;
    setParams?: (params: { color?: string; text_color?: string }) => void;
  };
  BackButton?: {
    show: () => void;
    hide: () => void;
    onClick: (cb: Callback) => void;
    offClick: (cb: Callback) => void;
  };
  CloudStorage?: {
    getItem: (key: string, cb: (error: unknown, value?: string) => void) => void;
    setItem: (key: string, value: string, cb?: (error: unknown) => void) => void;
  };
}

export interface TgFacade {
  readonly isTelegram: boolean;
  /** True when the client draws the main button itself; otherwise the page draws it. */
  readonly hasNativeMainButton: boolean;
  readonly colorScheme: ColorScheme;
  readonly startParam: string | null;
  /** The guest as Telegram knows them; null outside Telegram. */
  readonly user: { firstName: string; photoUrl: string | null } | null;
  ready(): void;
  expand(): void;
  disableVerticalSwipes(): void;
  onThemeChanged(cb: Callback): () => void;
  setChromeColor(hex: string): void;
  openLink(url: string): void;
  openTelegramLink(url: string): void;
  haptic: {
    impact(style: 'light' | 'medium'): void;
    selection(): void;
    notify(type: 'success' | 'warning' | 'error'): void;
  };
  mainButton: { set(state: MainButtonState | null): void };
  backButton: { set(onBack: Callback | null): void };
  closingConfirmation(enabled: boolean): void;
  storage: { get(key: string): Promise<string | null>; set(key: string, value: string): Promise<void> };
}

function createStore<T>(initial: T) {
  let value = initial;
  const listeners = new Set<Callback>();
  return {
    get: () => value,
    set(next: T) {
      value = next;
      listeners.forEach((l) => l());
    },
    subscribe(listener: Callback) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

/** Current bottom bar state; the page always draws it (spec v2 §5: Telegram's MainButton is not used). */
export const mainButtonStore = createStore<MainButtonState | null>(null);

function prefersDark(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return true;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function navigateInApp(url: string): boolean {
  if (!url.startsWith('#')) return false;
  window.location.hash = url.slice(1);
  return true;
}

const localStore = {
  async get(key: string) {
    return window.localStorage.getItem(key);
  },
  async set(key: string, value: string) {
    window.localStorage.setItem(key, value);
  },
};

/** The club accent stays fixed; Telegram would otherwise paint the button in its own theme colour. */
const MAIN_ENABLED = { color: '#FF7A3D', text_color: '#2B1205' };
const MAIN_DISABLED: Record<ColorScheme, { color: string; text_color: string }> = {
  dark: { color: '#2A262F', text_color: '#BDB6AE' },
  light: { color: '#E6E1DA', text_color: '#5A545C' },
};

export function createTg(web?: TelegramWebApp): TgFacade {
  let mainHandler: Callback | null = null;
  let backHandler: Callback | null = null;
  const native = web?.MainButton;

  return {
    isTelegram: Boolean(web),
    hasNativeMainButton: Boolean(native),
    get colorScheme(): ColorScheme {
      if (web) return web.colorScheme === 'light' ? 'light' : 'dark';
      return prefersDark() ? 'dark' : 'light';
    },
    startParam: web?.initDataUnsafe.start_param ?? null,
    user: web?.initDataUnsafe.user
      ? { firstName: web.initDataUnsafe.user.first_name, photoUrl: web.initDataUnsafe.user.photo_url ?? null }
      : null,
    ready: () => web?.ready?.(),
    expand: () => web?.expand?.(),
    disableVerticalSwipes: () => web?.disableVerticalSwipes?.(),
    onThemeChanged(cb) {
      if (web?.onEvent) {
        web.onEvent('themeChanged', cb);
        return () => web.offEvent?.('themeChanged', cb);
      }
      if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
        const media = window.matchMedia('(prefers-color-scheme: dark)');
        media.addEventListener('change', cb);
        return () => media.removeEventListener('change', cb);
      }
      return () => undefined;
    },
    setChromeColor(hex) {
      if (typeof web?.setHeaderColor === 'function') web.setHeaderColor(hex);
      if (typeof web?.setBackgroundColor === 'function') web.setBackgroundColor(hex);
      if (typeof web?.setBottomBarColor === 'function') web.setBottomBarColor(hex);
    },
    openLink(url) {
      if (navigateInApp(url)) return;
      if (web?.openLink) web.openLink(url);
      else window.open(url, '_blank', 'noopener');
    },
    openTelegramLink(url) {
      if (web?.openTelegramLink) web.openTelegramLink(url);
      else window.open(url, '_blank', 'noopener');
    },
    haptic: {
      impact: (style) => web?.HapticFeedback?.impactOccurred(style),
      selection: () => web?.HapticFeedback?.selectionChanged(),
      notify: (type) => web?.HapticFeedback?.notificationOccurred(type),
    },
    mainButton: {
      set(state) {
        mainButtonStore.set(state);
        if (!native) return;
        if (mainHandler) native.offClick(mainHandler);
        mainHandler = null;
        if (!state) {
          native.hideProgress();
          native.hide();
          return;
        }
        native.setText(state.text);
        native.setParams?.(state.enabled ? MAIN_ENABLED : MAIN_DISABLED[web?.colorScheme === 'light' ? 'light' : 'dark']);
        if (state.enabled) native.enable();
        else native.disable();
        if (state.progress) native.showProgress(false);
        else native.hideProgress();
        mainHandler = state.onClick;
        native.onClick(mainHandler);
        native.show();
      },
    },
    backButton: {
      set(onBack) {
        const back = web?.BackButton;
        if (!back) return;
        if (backHandler) back.offClick(backHandler);
        backHandler = onBack;
        if (onBack) {
          back.onClick(onBack);
          back.show();
        } else {
          back.hide();
        }
      },
    },
    closingConfirmation(enabled) {
      if (enabled) web?.enableClosingConfirmation?.();
      else web?.disableClosingConfirmation?.();
    },
    storage: web?.CloudStorage
      ? {
          get: (key) =>
            new Promise((resolve) =>
              web.CloudStorage!.getItem(key, (error, value) => resolve(error ? null : value || null)),
            ),
          set: (key, value) =>
            new Promise((resolve) => web.CloudStorage!.setItem(key, value, () => resolve())),
        }
      : localStore,
  };
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

function detect(): TelegramWebApp | undefined {
  if (typeof window === 'undefined') return undefined;
  const web = window.Telegram?.WebApp;
  // The SDK script defines WebApp everywhere; outside Telegram it has no init data.
  if (!web || !web.initData) return undefined;
  return web;
}

export const tg: TgFacade = createTg(detect());
