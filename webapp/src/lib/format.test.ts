import { describe, expect, it } from 'vitest';
import { billboardSubtitle, dayKey, formatDate, formatDateTime, formatDayMonth, formatPrice, formatTime, seatsLabel, shortDay, ticketsLabel } from './format';

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

describe('day keys', () => {
  it('takes the Moscow date of an instant', () => {
    expect(dayKey('2026-10-10T21:30:00Z', 'Europe/Moscow')).toBe('2026-10-11');
    expect(dayKey('2026-10-10T20:59:00Z', 'Europe/Moscow')).toBe('2026-10-10');
  });

  it('names the weekday and the day of a key', () => {
    expect(shortDay('2026-10-12')).toEqual({ dow: 'пн', day: 12 });
    expect(shortDay('2026-10-18')).toEqual({ dow: 'вс', day: 18 });
  });
});

describe('billboardSubtitle', () => {
  const tz = 'Europe/Moscow';
  // Saturday 10 Oct 2026, 12:00 in Moscow.
  const now = Date.parse('2026-10-10T09:00:00Z');

  it('says today and tomorrow with the time', () => {
    expect(billboardSubtitle('2026-10-10T17:00:00Z', tz, now)).toBe('Сегодня в 20:00');
    expect(billboardSubtitle('2026-10-11T17:00:00Z', tz, now)).toBe('Завтра в 20:00');
  });

  it('names the weekday within the next six days, in the right gender', () => {
    const wednesday = Date.parse('2026-10-07T09:00:00Z');
    expect(billboardSubtitle('2026-10-10T17:00:00Z', tz, wednesday)).toBe('Уже в эту субботу');
    expect(billboardSubtitle('2026-10-12T17:00:00Z', tz, now)).toBe('Уже в этот понедельник');
    expect(billboardSubtitle('2026-10-16T17:00:00Z', tz, now)).toBe('Уже в эту пятницу');
    expect(billboardSubtitle('2026-10-11T17:00:00Z', tz, wednesday)).toBe('Уже в это воскресенье');
  });

  it('falls back to the date further out', () => {
    expect(billboardSubtitle('2026-10-20T17:00:00Z', tz, now)).toBe('вт, 20 окт в 20:00');
  });
});

describe('formatDayMonth', () => {
  it('gives the day and the short month, without the dot', () => {
    expect(formatDayMonth('2026-10-25T20:00:00Z', 'Europe/Moscow')).toBe('25 окт');
    expect(formatDayMonth('2026-09-20T17:00:00Z', 'Europe/Moscow')).toBe('20 сент');
  });
});
