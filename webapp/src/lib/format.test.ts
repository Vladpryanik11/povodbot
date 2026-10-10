import { describe, expect, it } from 'vitest';
import { formatDate, formatDateTime, formatPrice, formatTime, seatsLabel, ticketsLabel } from './format';

const NB = ' ';

describe('ticketsLabel', () => {
  it.each([
    [1, '1 билет'],
    [2, '2 билета'],
    [4, '4 билета'],
    [5, '5 билетов'],
    [11, '11 билетов'],
    [14, '14 билетов'],
    [21, '21 билет'],
    [22, '22 билета'],
    [25, '25 билетов'],
    [111, '111 билетов'],
  ])('%i → %s', (n, expected) => {
    expect(ticketsLabel(n)).toBe(expected);
  });
});

describe('seatsLabel', () => {
  it('uses the right form and says when nothing is left', () => {
    expect(seatsLabel(1)).toBe('осталось 1 место');
    expect(seatsLabel(2)).toBe('осталось 2 места');
    expect(seatsLabel(5)).toBe('осталось 5 мест');
    expect(seatsLabel(0)).toBe('мест нет');
  });
});

describe('dates in the event timezone', () => {
  const iso = '2026-10-16T17:00:00Z';
  it('formats weekday, day and short month without dots', () => {
    expect(formatDate(iso, 'Europe/Moscow')).toBe('пт, 16 окт');
  });
  it('formats 24-hour time', () => {
    expect(formatTime(iso, 'Europe/Moscow')).toBe('20:00');
  });
  it('joins date and time with a middle dot', () => {
    expect(formatDateTime(iso, 'Europe/Moscow')).toBe('пт, 16 окт · 20:00');
  });
});

describe('formatPrice', () => {
  it('groups thousands and the ruble sign with non-breaking spaces', () => {
    expect(formatPrice(155000)).toBe(`1${NB}550${NB}₽`);
    expect(formatPrice(310000)).toBe(`3${NB}100${NB}₽`);
    expect(formatPrice(90000)).toBe(`900${NB}₽`);
  });
});
