import { describe, expect, it } from 'vitest';
import { POSTER_COLORS, posterColor } from './posterColor';

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
