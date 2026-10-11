import { afterEach, describe, expect, it, vi } from 'vitest';
import { MSG } from '../owner/messages';
import { OwnerApiError } from '../owner/OwnerApi';
import { QuietHoursError } from './CampaignApi';
import { HttpCampaignApi } from './HttpCampaignApi';

function stubFetch(status: number, body: unknown) {
  const fetch = vi.fn(async () =>
    body === undefined ? new Response(null, { status }) : new Response(JSON.stringify(body), { status }),
  );
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

const api = () => new HttpCampaignApi(() => 'signed');
const sent = (fetch: ReturnType<typeof stubFetch>) => fetch.mock.calls[0] as unknown as [string, RequestInit];

describe('HttpCampaignApi', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('signs in with initData and sends JSON', async () => {
    const fetch = stubFetch(200, { count: 3, overLimit: 0 });
    const filter = { event: null, directionId: null, purchases: 'any' as const };
    expect(await api().audienceCount(filter)).toEqual({ count: 3, overLimit: 0 });
    const [url, init] = sent(fetch);
    expect(url).toBe('/api/owner/campaigns/audience-count');
    expect(init.method).toBe('POST');
    expect(init.headers).toMatchObject({ Authorization: 'tma signed', 'Content-Type': 'application/json' });
    expect(JSON.parse(init.body as string)).toEqual(filter);
  });

  it('lists by filter and sends now with an empty body', async () => {
    let fetch = stubFetch(200, []);
    await api().campaigns('scheduled');
    expect(sent(fetch)[0]).toBe('/api/owner/campaigns?filter=scheduled');
    fetch = stubFetch(200, {});
    await api().send('c1', null);
    expect(sent(fetch)[0]).toBe('/api/owner/campaigns/c1/send');
    expect(JSON.parse(sent(fetch)[1].body as string)).toEqual({});
  });

  it('takes 204 for the test send and template removal', async () => {
    let fetch = stubFetch(204, undefined);
    await expect(api().sendTest('c1')).resolves.toBeUndefined();
    expect(sent(fetch)[0]).toBe('/api/owner/campaigns/c1/test');
    fetch = stubFetch(204, undefined);
    await api().deleteTemplate('t1');
    expect(sent(fetch)).toEqual(['/api/owner/campaign-templates/t1', expect.objectContaining({ method: 'DELETE' })]);
  });

  it('uploads the picture as a file field', async () => {
    const fetch = stubFetch(200, {});
    await api().uploadImage('c1', new File(['x'], 'a.png', { type: 'image/png' }));
    const [url, init] = sent(fetch);
    expect(url).toBe('/api/owner/campaigns/c1/image');
    expect((init.body as FormData).get('file')).toBeInstanceOf(File);
    expect(init.headers).not.toHaveProperty('Content-Type');
  });

  it('turns the night answer into QuietHoursError and fields into OwnerApiError', async () => {
    stubFetch(422, { field: 'at', message: 'Ночью не отправляем. Отправить в 10:00?', suggestedAt: '2026-10-11T07:00:00Z' });
    const night = await api().send('c1', null).catch((e: unknown) => e);
    expect(night).toBeInstanceOf(QuietHoursError);
    expect((night as QuietHoursError).suggestedAt).toBe('2026-10-11T07:00:00Z');

    stubFetch(422, { field: 'eventId', message: 'Вечер больше не опубликован' });
    const gone = await api().send('c1', null).catch((e: unknown) => e);
    expect(gone).toMatchObject({ status: 422, field: 'eventId', message: 'Вечер больше не опубликован' });
  });

  it('says there is no network when fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('offline'))));
    const error = await api().campaign('c1').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(OwnerApiError);
    expect(error).toMatchObject({ status: 0, message: MSG.network });
  });
});
