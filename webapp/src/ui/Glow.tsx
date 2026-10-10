import { createContext, createElement, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import styles from './Glow.module.css';

type SetGlow = (color: string | null) => void;

function paint(color: string | null): void {
  const root = document.documentElement.style;
  if (color) root.setProperty('--poster', color);
  else root.removeProperty('--poster');
}

const GlowContext = createContext<{ color: string | null; set: SetGlow }>({ color: null, set: paint });

/** Holds the poster colour of the screen on top; writes it to --poster on <html>. */
export function GlowProvider({ children }: { children: ReactNode }) {
  const [color, set] = useState<string | null>(null);
  useEffect(() => paint(color), [color]);
  return createElement(GlowContext.Provider, { value: { color, set } }, children);
}

/** The calling screen tints the glow while mounted; unmount clears it. */
export function useGlow(color: string | null): void {
  const { set } = useContext(GlowContext);
  useEffect(() => {
    set(color);
    return () => set(null);
  }, [set, color]);
}

/** Poster-coloured halo at the top of the screen, behind the content (spec v2 §3). */
export function Glow() {
  const { color } = useContext(GlowContext);
  return <div className={styles.glow} data-glow="" data-off={color ? undefined : ''} aria-hidden="true" />;
}
