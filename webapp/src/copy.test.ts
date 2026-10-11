import { describe, expect, it } from 'vitest';

const sources = import.meta.glob(['./**/*.tsx', '!./**/*.test.tsx'], { query: '?raw', import: 'default', eager: true }) as Record<
  string,
  string
>;

/** The v2 voice is «ты» (spec v2 §8); these give the old polite «вы» away. */
const FORMAL = /(?<![а-яё])(выберите|проверьте|попробуйте|загляните|попросите|откройте|напишите|у вас|вами|вам|ваш[а-яё]*)(?![а-яё])/giu;
/** The polls tab is gone from the navigation; its title survives only on the parked Polls screen. */
const POLLS_TAB = /Голосуем/g;

describe('copy', () => {
  it('scans the app sources', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(20);
  });

  it('speaks on «ты» everywhere', () => {
    const hits = Object.entries(sources).flatMap(([file, text]) => [...text.matchAll(FORMAL)].map((m) => `${file}: ${m[0]}`));
    expect(hits).toEqual([]);
  });

  it('has no «Голосуем» outside the parked polls screen', () => {
    const hits = Object.entries(sources)
      .filter(([file]) => file !== './screens/Polls.tsx')
      .flatMap(([file, text]) => [...text.matchAll(POLLS_TAB)].map(() => file));
    expect(hits).toEqual([]);
  });
});
