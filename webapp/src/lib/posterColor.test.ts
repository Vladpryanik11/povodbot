import { afterEach, describe, expect, it, vi } from 'vitest';
import { POSTER_COLORS, dominantColor, eventColor, extractPosterColor, normalizeHsl, posterColor } from './posterColor';

describe('posterColor', () => {
  it('is one of the eight contrast-checked colours', () => {
    expect(POSTER_COLORS).toEqual([
      '#5B2A86',
      '#8A3A1A',
      '#1F5C4D',
      '#7A2840',
      '#2B3F7A',
      '#7A5A14',
      '#3E4A1F',
      '#2F5F73',
    ]);
    expect(POSTER_COLORS).toContain(posterColor('Повод для киновечера'));
  });

  it('is stable for the same title and varies between titles', () => {
    expect(posterColor('Настолки до утра')).toBe(posterColor('Настолки до утра'));
    const titles = ['Кино', 'Настолки', 'Разговоры', 'Вечеринка', 'Квартирник', 'Лекция'];
    expect(new Set(titles.map(posterColor)).size).toBeGreaterThan(1);
  });
});

function hexToHsl(hex: string): { h: number; s: number; l: number } {
  const n = parseInt(hex.slice(1), 16);
  const r = ((n >> 16) & 255) / 255;
  const g = ((n >> 8) & 255) / 255;
  const b = (n & 255) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  const d = max - min;
  if (d === 0) return { h: 0, s: 0, l: l * 100 };
  const s = d / (1 - Math.abs(2 * l - 1));
  let h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  h = (h * 60 + 360) % 360;
  return { h, s: s * 100, l: l * 100 };
}

function pixels(hex: string, count: number): number[] {
  const n = parseInt(hex.slice(1), 16);
  return Array.from({ length: count }, () => [(n >> 16) & 255, (n >> 8) & 255, n & 255, 255]).flat();
}

describe('normalizeHsl', () => {
  it('keeps a white poster from burning the screen', () => {
    const { l } = hexToHsl(normalizeHsl('#FFFFFF'));
    expect(l).toBeLessThanOrEqual(60.5);
  });

  it('lifts a near-black colour', () => {
    expect(hexToHsl(normalizeHsl('#101010')).l).toBeGreaterThanOrEqual(44.5);
  });

  it('tames pure red', () => {
    expect(hexToHsl(normalizeHsl('#FF0000')).s).toBeLessThanOrEqual(80.5);
  });

  it('returns #rrggbb', () => {
    expect(normalizeHsl('#2244FF')).toMatch(/^#[0-9a-f]{6}$/);
  });
});

describe('dominantColor', () => {
  it('finds the hue of the poster and ignores black pixels', () => {
    const data = new Uint8ClampedArray([...pixels('#D4537E', 100), ...pixels('#000000', 20)]);
    const hex = dominantColor(data);
    expect(hex).not.toBeNull();
    expect(Math.abs(hexToHsl(hex as string).h - 340)).toBeLessThanOrEqual(10);
  });

  it('gives up on a white poster', () => {
    expect(dominantColor(new Uint8ClampedArray(pixels('#FFFFFF', 100)))).toBeNull();
  });
});

describe('eventColor', () => {
  it('prefers the organiser accent colour', () => {
    expect(eventColor({ accentColor: '#2244FF', title: 'x' }, '#00FF00')).toBe(normalizeHsl('#2244FF'));
  });

  it('falls back to the title hash without poster or accent', () => {
    expect(eventColor({ accentColor: null, title: 'Киновечер' }, null)).toBe(normalizeHsl(posterColor('Киновечер')));
  });

  it('uses the extracted colour when there is no accent', () => {
    expect(eventColor({ accentColor: null, title: 'x' }, '#00AA44')).toBe(normalizeHsl('#00AA44'));
  });
});

describe('extractPosterColor', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('resolves null when the image fails to load', async () => {
    vi.stubGlobal(
      'Image',
      class {
        onload: (() => void) | null = null;
        onerror: (() => void) | null = null;
        crossOrigin = '';
        set src(_: string) {
          setTimeout(() => this.onerror?.(), 0);
        }
      },
    );
    await expect(extractPosterColor('/broken.jpg')).resolves.toBeNull();
  });
});
