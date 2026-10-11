import { describe, expect, it } from 'vitest';
import { T0 } from '../../test/render';
import { OwnerApiError } from '../owner/OwnerApi';
import { MSG } from '../owner/messages';
import { QuietHoursError } from './CampaignApi';
import { CMSG } from './messages';
import { MockCampaignApi } from './MockCampaignApi';
import { EMPTY_AUDIENCE } from './types';

const make = (options: ConstructorParameters<typeof MockCampaignApi>[0] = {}) =>
  new MockCampaignApi({ latencyMs: 0, now: () => T0, ...options });

async function rejection(promise: Promise<unknown>): Promise<OwnerApiError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof OwnerApiError) return error;
    throw error;
  }
  throw new Error('expected a rejection');
}

describe('MockCampaignApi', () => {
  it('splits the list by filter in the server order', async () => {
    const api = make();
    expect((await api.campaigns('draft')).map((c) => c.id)).toEqual(['c-draft', 'c-gone']);
    expect((await api.campaigns('scheduled')).map((c) => c.id)).toEqual(['c-scheduled']);
    const sent = await api.campaigns('sent');
    expect(sent.map((c) => c.id)).toEqual(['c-cancelled', 'c-running', 'c-stopped', 'c-done']);
    expect(sent.find((c) => c.id === 'c-done')).toMatchObject({ delivered: 205, clicked: 37 });
  });

  it('fills the event cover for an event image', async () => {
    const c = await make().campaign('c-draft');
    expect(c.image).toEqual({ kind: 'event', url: './mock/kino.jpg' });
  });

  it('turns away a stale version', async () => {
    const api = make();
    const c = await api.campaign('c-draft');
    await api.updateCampaign(c.id, { title: 'Раз', updatedAt: c.updatedAt });
    const error = await rejection(api.updateCampaign(c.id, { title: 'Два', updatedAt: c.updatedAt }));
    expect(error.status).toBe(409);
    expect(error.message).toBe(CMSG.stale);
  });

  it('rejects bare <, > and & in the body like the server', async () => {
    const api = make();
    const c = await api.campaign('c-draft');
    const error = await rejection(api.updateCampaign(c.id, { body: 'a < b', updatedAt: c.updatedAt }));
    expect([error.status, error.field, error.message]).toEqual([422, 'body', CMSG.onlyTags]);
  });

  it('counts the caption limit in UTF-16 units', async () => {
    const api = make();
    const c = await api.campaign('c-draft');
    const error = await rejection(
      api.updateCampaign(c.id, { body: 'a'.repeat(1023) + '😀', updatedAt: c.updatedAt }),
    );
    expect([error.field, error.message]).toEqual(['body', CMSG.tooLong]);
  });

  it('does not let an unpublished event in on edit', async () => {
    const error = await rejection(make().createCampaign({ eventId: 'e-own-workshop' }));
    expect([error.field, error.message]).toEqual(['eventId', CMSG.eventNotPublished]);
  });

  it('says the event is gone when sending', async () => {
    const error = await rejection(make().send('c-gone', null));
    expect([error.field, error.message]).toEqual(['eventId', CMSG.eventGone]);
  });

  it('counts the audience deterministically', async () => {
    const api = make();
    expect(await api.audienceCount(EMPTY_AUDIENCE)).toEqual({ count: 214, overLimit: 9 });
    const going = (id: string) => ({ ...EMPTY_AUDIENCE, event: { id, relation: 'going' as const } });
    expect(await api.audienceCount(going('e-own-film'))).toEqual({ count: 18, overLimit: 0 });
    expect(await api.audienceCount(going('e-own-free'))).toEqual({ count: 0, overLimit: 0 });
  });

  it('will not send to nobody', async () => {
    const api = make();
    const c = await api.campaign('c-draft');
    await api.updateCampaign(c.id, {
      audience: { ...EMPTY_AUDIENCE, event: { id: 'e-own-free', relation: 'going' } },
      updatedAt: c.updatedAt,
    });
    const error = await rejection(api.send(c.id, null));
    expect([error.field, error.message]).toEqual(['audience', CMSG.noRecipients]);
  });

  it('sends now in the daytime', async () => {
    const c = await make().send('c-draft', null);
    expect(c).toMatchObject({ status: 'running', recipientCount: 37 });
    expect(c.startedAt).toBe(new Date(T0).toISOString());
  });

  it('offers 10:00 when sending now at night', async () => {
    const night = Date.parse('2026-10-10T20:00:00Z'); // 23:00 Moscow
    const error = await rejection(make({ now: () => night }).send('c-draft', null));
    expect(error).toBeInstanceOf(QuietHoursError);
    expect(error.message).toBe(CMSG.night);
    expect((error as QuietHoursError).suggestedAt).toBe('2026-10-11T07:00:00.000Z');
  });

  it('schedules up to 21:59 and not from 22:00 Moscow time', async () => {
    const api = make();
    const quiet = await rejection(api.send('c-draft', '2026-10-10T22:00:00+03:00'));
    expect([quiet.field, quiet.message]).toEqual(['at', CMSG.quietAt]);
    const past = await rejection(api.send('c-draft', '2026-10-10T11:00:00+03:00'));
    expect([past.field, past.message]).toEqual(['at', CMSG.past]);
    const c = await api.send('c-draft', '2026-10-10T21:59:00+03:00');
    expect(c).toMatchObject({ status: 'scheduled', scheduledAt: '2026-10-10T18:59:00.000Z' });
  });

  it('cancels only a scheduled one and stops only a running one', async () => {
    const api = make();
    expect((await api.cancel('c-scheduled')).status).toBe('cancelled');
    expect((await rejection(api.cancel('c-draft'))).message).toBe(CMSG.cancelOnlyScheduled);
    expect((await api.stop('c-running')).status).toBe('stopped');
    expect((await rejection(api.stop('c-done'))).message).toBe(CMSG.stopOnlyRunning);
    expect((await rejection(api.updateCampaign('c-done', { title: 'x', updatedAt: '' }))).message).toBe(
      CMSG.locked,
    );
  });

  it('duplicates into a draft copy', async () => {
    const copy = await make().duplicate('c-done');
    expect(copy).toMatchObject({ status: 'draft', title: 'Спасибо за «Сталкера» (копия)' });
  });

  it('keeps the ready templates locked', async () => {
    const api = make();
    const templates = await api.templates();
    expect(templates.filter((t) => t.isBuiltin).map((t) => t.name)).toEqual([
      'Вечер перенесён',
      'Завтра вечер',
      'Новый вечер в афише',
      'Осталось мало мест',
      'Спасибо, что пришли',
    ]);
    const builtin = templates[0];
    const error = await rejection(api.updateTemplate(builtin.id, { name: 'x' }));
    expect([error.status, error.message]).toEqual([403, CMSG.builtinLocked]);
    expect((await rejection(api.createTemplate({ name: ' ' }))).message).toBe(CMSG.emptyName);
  });

  it('saves a campaign as a template', async () => {
    const api = make();
    const t = await api.saveAsTemplate('c-draft', 'Анонс');
    const c = await api.campaign('c-draft');
    expect(t).toMatchObject({ name: 'Анонс', body: c.body, imageKind: 'event', isBuiltin: false });
  });

  it('cannot reach a guest who never opened the bot', async () => {
    const error = await rejection(make({ telegramLinked: false }).sendTest('c-draft'));
    expect([error.status, error.message]).toEqual([422, CMSG.botBlocked]);
  });

  it('turns away the door staff and works offline-aware', async () => {
    expect((await rejection(make({ role: 'entrance' }).campaigns('draft'))).message).toBe(MSG.noAccess);
    expect((await rejection(make({ offline: true }).campaigns('draft'))).status).toBe(0);
  });
});
