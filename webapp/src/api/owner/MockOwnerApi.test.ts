import { describe, expect, it } from 'vitest';
import { MSG } from './messages';
import { MockOwnerApi, ownerRoleFromUrl } from './MockOwnerApi';
import type { OwnerEventInput } from './types';

const T0 = Date.parse('2026-10-10T09:00:00Z');

function api(options: ConstructorParameters<typeof MockOwnerApi>[0] = {}) {
  return new MockOwnerApi({ latencyMs: 0, now: () => T0, ...options });
}

const INPUT: OwnerEventInput = {
  title: 'Новый вечер',
  description: 'Что-то хорошее',
  directionId: 'd-film',
  startsAt: '2026-10-20T19:00:00+03:00',
  endsAt: '2026-10-20T23:00:00+03:00',
  timezone: 'Europe/Moscow',
  address: null,
  capacity: 20,
  mapUrl: null,
  accentColor: null,
  ticketTypes: [{ name: 'Входной', priceKopecks: 50000, limit: 20 }],
};

describe('MockOwnerApi', () => {
  it('reads the role from the URL', () => {
    expect(ownerRoleFromUrl('?owner=guest')).toBe('guest');
    expect(ownerRoleFromUrl('?owner=entrance')).toBe('entrance');
    expect(ownerRoleFromUrl('?owner=boss')).toBe('owner');
  });

  it('lets the owner in and keeps guests and door staff out', async () => {
    expect((await api().me()).permissions).toContain('manage_events');
    await expect(api({ role: 'guest' }).me()).rejects.toMatchObject({ status: 403, message: MSG.noAccess });
    expect((await api({ role: 'entrance' }).me()).permissions).not.toContain('manage_events');
    await expect(api({ role: 'entrance' }).events('all')).rejects.toMatchObject({ status: 403 });
    await expect(api({ offline: true }).events('all')).rejects.toMatchObject({ status: 0, message: MSG.network });
  });

  it('filters like the server', async () => {
    const a = api();
    expect((await a.events('all')).map((e) => e.id)).toEqual([
      'e-own-film',
      'e-own-free',
      'e-own-workshop',
      'e-own-book',
      'e-own-legacy',
    ]);
    expect((await a.events('draft')).every((e) => e.status === 'draft')).toBe(true);
    expect((await a.events('past')).map((e) => e.id)).toEqual(['e-own-past']);
  });

  it('creates a draft and rejects a stale version', async () => {
    const a = api();
    const created = await a.createEvent(INPUT);
    expect(created).toMatchObject({ status: 'draft', poster: null, sold: 0 });
    const saved = await a.updateEvent(created.id, { updatedAt: created.updatedAt, title: 'Другое' });
    expect(saved.updatedAt).not.toBe(created.updatedAt);
    await expect(a.updateEvent(created.id, { updatedAt: created.updatedAt, title: 'Третье' })).rejects.toMatchObject({
      status: 409,
      message: MSG.conflict,
    });
    await expect(a.createEvent({ ...INPUT, title: ' ' })).rejects.toMatchObject({
      status: 422,
      field: 'title',
      message: MSG.title,
    });
  });

  it('keeps saved ticket rows and switches off the dropped ones', async () => {
    const a = api();
    const e = await a.event('e-own-workshop');
    const saved = await a.updateEvent(e.id, {
      updatedAt: e.updatedAt,
      ticketTypes: [{ name: 'Новый', priceKopecks: 0, limit: 5 }],
    });
    expect(saved.ticketTypes.filter((t) => t.active).map((t) => t.name)).toEqual(['Новый']);
    expect(saved.ticketTypes.length).toBe(e.ticketTypes.length + 1);
  });

  it('publishes only with a poster and unpublishes only without sales', async () => {
    const a = api();
    await expect(a.publish('e-own-book')).rejects.toMatchObject({ status: 422, field: 'poster', message: MSG.needPoster });
    expect((await a.publish('e-own-workshop')).status).toBe('published');
    await expect(a.unpublish('e-own-film')).rejects.toMatchObject({ status: 409, message: MSG.hasOrders });
    expect((await a.unpublish('e-own-free')).status).toBe('draft');
  });

  it('checks the photo before taking it', async () => {
    const a = api();
    const big = new File(['x'], 'big.jpg', { type: 'image/jpeg' });
    Object.defineProperty(big, 'size', { value: 15 * 1024 * 1024 + 1 });
    await expect(a.uploadPoster('e-own-book', big, { x: 0.5, y: 0.5 })).rejects.toMatchObject({ status: 413, field: 'poster' });
    await expect(
      a.uploadPoster('e-own-book', new File(['x'], 'a.pdf', { type: 'application/pdf' }), { x: 0.5, y: 0.5 }),
    ).rejects.toMatchObject({ status: 415 });
    const before = await a.event('e-own-book');
    const after = await a.uploadPoster('e-own-book', new File(['x'], 'a.heic', { type: 'image/heic' }), { x: 0.3, y: 0.4 });
    expect(after.poster).toMatchObject({ focusX: 0.3, focusY: 0.4, width: 1080 });
    expect(after.updatedAt).not.toBe(before.updatedAt);
  });

  it('takes one upload at a time', async () => {
    const a = api({ latencyMs: 20 });
    const file = new File(['x'], 'a.jpg', { type: 'image/jpeg' });
    const first = a.uploadPoster('e-own-book', file, { x: 0.5, y: 0.5 });
    await expect(a.uploadPoster('e-own-book', file, { x: 0.5, y: 0.5 })).rejects.toMatchObject({
      status: 429,
      message: MSG.uploadBusy,
    });
    await first;
  });

  it('hands out copies, not its own state', async () => {
    const a = api();
    const e = await a.event('e-own-film');
    e.title = 'Испорчено';
    e.ticketTypes[0].name = 'Испорчено';
    const again = await a.event('e-own-film');
    expect([again.title, again.ticketTypes[0].name]).not.toContain('Испорчено');
  });
});
