import { createContext, createElement, useContext, useEffect, useRef, useSyncExternalStore } from 'react';
import type { ReactNode } from 'react';
import { mainButtonStore, tg as defaultTg, type MainButtonState, type TgFacade } from './tg';

const TgContext = createContext<TgFacade>(defaultTg);

export function TgProvider({ value, children }: { value: TgFacade; children: ReactNode }) {
  return createElement(TgContext.Provider, { value }, children);
}

export function useTg(): TgFacade {
  return useContext(TgContext);
}

/** The app is dark only; the Telegram header and overscroll take this colour. */
export const THEME_BG = '#000000';

/** Forces the dark theme whatever Telegram's colorScheme says. */
export function useTheme(): 'dark' {
  const tg = useTg();

  useEffect(() => {
    document.documentElement.dataset.theme = 'dark';
    tg.setChromeColor(THEME_BG);
  }, [tg]);

  return 'dark';
}

type MainButtonInput = Omit<MainButtonState, 'onClick'> & { onClick: () => void };

/**
 * Shows the page bottom bar while the calling screen is mounted. Re-registers only when text or state change.
 * Writes to the store only: Telegram's MainButton can't be styled to match, so the page draws its own (spec v2 §5).
 */
export function useMainButton(state: MainButtonInput | null): void {
  const latest = useRef(state?.onClick);
  latest.current = state?.onClick;
  const text = state?.text;
  const enabled = state?.enabled;
  const progress = state?.progress;
  const summary = state?.summary;
  const visible = state !== null;

  useEffect(() => {
    mainButtonStore.set(
      visible
        ? { text: text ?? '', enabled: Boolean(enabled), progress: Boolean(progress), summary, onClick: () => latest.current?.() }
        : null,
    );
  }, [visible, text, enabled, progress, summary]);

  useEffect(() => () => mainButtonStore.set(null), []);
}

export function useBackButton(onBack: (() => void) | null): void {
  const tg = useTg();
  const latest = useRef(onBack);
  latest.current = onBack;
  const visible = onBack !== null;

  useEffect(() => {
    tg.backButton.set(visible ? () => latest.current?.() : null);
    return () => tg.backButton.set(null);
  }, [tg, visible]);
}

export function useClosingConfirmation(enabled: boolean): void {
  const tg = useTg();
  useEffect(() => {
    tg.closingConfirmation(enabled);
  }, [tg, enabled]);
}

export function useMainButtonState(): MainButtonState | null {
  return useSyncExternalStore(mainButtonStore.subscribe, mainButtonStore.get);
}
