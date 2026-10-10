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
