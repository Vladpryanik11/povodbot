import { describe, expect, it } from 'vitest';
import { MSG } from '../api/owner/messages';
import type { OwnerEvent } from '../api/owner/types';
import {
  emptyForm,
  formatRubles,
  formFromEvent,
  formToInput,
  fromZonedIso,
  parseCount,
  parseRubles,
  publishGaps,
  toPreviewDetail,
  toZonedIso,
} from './form';

const T0 = Date.parse('2026-10-10T09:00:00Z');

const EVENT: OwnerEvent = {
  id: 'e1',
  title: 'Кино на крыше',
  description: 'Смотрим и спорим',
  directionId: 'd1',
  startsAt: '2026-10-20T16:00:00Z',
  endsAt: '2026-10-20T19:00:00Z',
  timezone: 'Europe/Moscow',
  address: 'Покровка, 1',
  mapUrl: null,
  capacity: 30,
  ticketTypes: [{ id: 't1', name: 'Входной', priceKopecks: 150000, currency: 'RUB', limit: 30, active: true }],
  status: 'draft',
  publishedAt: null,
  createdAt: '2026-10-01T10:00:00Z',
  updatedAt: '2026-10-01T10:00:00.123456+00:00',
  accentColor: null,
  poster: { url: '/media/posters/a-1080.webp', focusX: 0.5, focusY: 0.4, width: 1080, height: 1350 },
  sold: 0,
};

describe('owner event form', () => {
  it('converts Moscow wall time both ways', () => {
    expect(toZonedIso('2026-10-20T19:00', 'Europe/Moscow')).toBe('2026-10-20T19:00:00+03:00');
    expect(fromZonedIso('2026-10-20T16:00:00Z', 'Europe/Moscow')).toBe('2026-10-20T19:00');
    expect(fromZonedIso('2026-10-20T16:00:00.123456+00:00', 'Europe/Moscow')).toBe('2026-10-20T19:00');
  });

  it('reads rubles the way people type them', () => {
    expect(parseRubles('1 500')).toBe(150000);
    expect(parseRubles('1500,50')).toBe(150050);
    expect(parseRubles('1 500.5')).toBe(150050);
    expect(parseRubles('0')).toBe(0);
    for (const bad of ['', '-5', '12,345', 'abc']) expect(parseRubles(bad)).toBeNull();
    expect(formatRubles(150050)).toBe('1500,50');
    expect(formatRubles(150000)).toBe('1500');
    expect(parseCount('30')).toBe(30);
    for (const bad of ['', '0', '2.5', '-1']) expect(parseCount(bad)).toBeNull();
  });

  it('round-trips an event through the form', () => {
    const input = formToInput(formFromEvent(EVENT));
    expect(input).toEqual({
      ok: true,
      input: expect.objectContaining({
        startsAt: '2026-10-20T19:00:00+03:00',
        address: 'Покровка, 1',
        mapUrl: null,
        accentColor: null,
        ticketTypes: [{ id: 't1', name: 'Входной', priceKopecks: 150000, limit: 30, currency: 'RUB', active: true }],
      }),
    });
  });

  it('sends null for the venue when it is still being decided', () => {
    const form = { ...formFromEvent(EVENT), venueTbd: true, address: 'старый' };
    expect(formToInput(form)).toMatchObject({ ok: true, input: { address: null } });
  });

  it('names the first field it cannot send', () => {
    expect(formToInput({ ...emptyForm(), title: 'x' })).toEqual({ ok: false, field: 'directionId', message: MSG.direction });
    const base = formFromEvent(EVENT);
    expect(formToInput({ ...base, endsLocal: '' })).toMatchObject({ field: 'endsAt', message: MSG.dateTime });
    expect(formToInput({ ...base, capacity: 'много' })).toMatchObject({ field: 'capacity', message: MSG.capacity });
    expect(formToInput({ ...base, tickets: [{ ...base.tickets[0], price: 'дорого' }] })).toMatchObject({
      field: 'ticketTypes',
      message: MSG.ticketPrice,
    });
  });

  it('lists what publishing still needs', () => {
    expect(publishGaps(emptyForm(), false)).toEqual([
      'название',
      'направление',
      'дату и время',
      'адрес',
      'описание',
      'вместимость',
      'билет',
      'фото',
    ]);
    expect(publishGaps({ ...formFromEvent(EVENT), venueTbd: true, address: '' }, true)).toEqual([]);
    const off = formFromEvent(EVENT);
    off.tickets[0].active = false;
    expect(publishGaps(off, true)).toEqual(['билет']);
  });

  it('builds the guest view from unsaved input', () => {
    const form = { ...formFromEvent(EVENT), title: 'Новое имя', capacity: '20' };
    const detail = toPreviewDetail(form, { ...EVENT, sold: 5 }, T0);
    expect(detail).toMatchObject({
      title: 'Новое имя',
      seatsLeft: 15,
      soldOut: false,
      minPriceKopecks: 150000,
      poll: null,
      attendees: { count: 0, avatars: [] },
    });
    expect(toPreviewDetail({ ...emptyForm(), capacity: 'x' }, undefined, T0)).toMatchObject({
      seatsLeft: 0,
      ticketTypes: [],
      poster: null,
    });
  });
});
