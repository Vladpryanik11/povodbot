/** Backgrounds for events without a usable photo; each passes 4.5:1 with the light text colour. */
export const POSTER_COLORS = [
  '#5B2A86',
  '#8A3A1A',
  '#1F5C4D',
  '#7A2840',
  '#2B3F7A',
  '#7A5A14',
  '#3E4A1F',
  '#2F5F73',
] as const;

/** FNV-1a 32-bit hash of the title picks the colour, so it never changes between visits. */
export function posterColor(title: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < title.length; i++) {
    hash ^= title.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return POSTER_COLORS[hash % POSTER_COLORS.length];
}

type Hsl = { h: number; s: number; l: number };

function rgbToHsl(r: number, g: number, b: number): Hsl {
  r /= 255;
  g /= 255;
  b /= 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  const d = max - min;
  if (d === 0) return { h: 0, s: 0, l };
  const s = d / (1 - Math.abs(2 * l - 1));
  let h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  h = (h * 60 + 360) % 360;
  return { h, s, l };
}

function hslToHex({ h, s, l }: Hsl): string {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  const [r, g, b] =
    h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  return '#' + [r, g, b].map((v) => Math.round((v + m) * 255).toString(16).padStart(2, '0')).join('');
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** Clamps a colour into S ∈ [45%, 80%], L ∈ [45%, 60%], so the glow is vivid but never burns the screen. */
export function normalizeHsl(hex: string): string {
  const n = parseInt(hex.replace('#', '').slice(0, 6), 16) || 0;
  const { h, s, l } = rgbToHsl((n >> 16) & 255, (n >> 8) & 255, n & 255);
  return hslToHex({ h, s: clamp(s, 0.45, 0.8), l: clamp(l, 0.45, 0.6) });
}

/** Median hue of the saturated mid-tone pixels of an RGBA buffer; null when fewer than 5% survive. */
export function dominantColor(pixels: Uint8ClampedArray): string | null {
  const total = Math.floor(pixels.length / 4);
  const hues: number[] = [];
  let sSum = 0;
  let lSum = 0;
  for (let i = 0; i + 3 < pixels.length; i += 4) {
    const px = rgbToHsl(pixels[i], pixels[i + 1], pixels[i + 2]);
    if (px.l < 0.15 || px.l > 0.9 || px.s < 0.2) continue;
    hues.push(px.h);
    sSum += px.s;
    lSum += px.l;
  }
  if (total === 0 || hues.length < total * 0.05) return null;
  hues.sort((a, b) => a - b);
  const h = hues[Math.floor(hues.length / 2)];
  return hslToHex({ h, s: sSum / hues.length, l: lSum / hues.length });
}

/** One colour per event: organiser's accent → colour extracted from the poster → title hash. */
export function eventColor(e: { accentColor: string | null; title: string }, extracted?: string | null): string {
  return normalizeHsl(e.accentColor ?? extracted ?? posterColor(e.title));
}

const extracted = new Map<string, Promise<string | null>>();

/** Samples the poster at 32×32; any failure (CORS, decode, no canvas) gives null. Cached per url. */
export function extractPosterColor(url: string): Promise<string | null> {
  const cached = extracted.get(url);
  if (cached) return cached;
  const result = new Promise<string | null>((resolve) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      try {
        const canvas = document.createElement('canvas');
        canvas.width = 32;
        canvas.height = 32;
        const ctx = canvas.getContext('2d');
        if (!ctx) return resolve(null);
        ctx.drawImage(img, 0, 0, 32, 32);
        resolve(dominantColor(ctx.getImageData(0, 0, 32, 32).data));
      } catch {
        resolve(null);
      }
    };
    img.onerror = () => resolve(null);
    img.src = url;
  });
  extracted.set(url, result);
  return result;
}
