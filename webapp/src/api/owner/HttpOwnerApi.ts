import { MSG } from './messages';
import { OwnerApiError, parseOwnerError, type OwnerApi } from './OwnerApi';
import type { Focus, OwnerEvent, OwnerEventInput, OwnerEventPatch } from './types';

/** Real /api/owner client. Same origin as the Mini App (Caddy), signed in with Telegram initData. */
export class HttpOwnerApi implements OwnerApi {
  constructor(
    private readonly initData: () => string,
    private readonly base = '/api/owner',
  ) {}

  private async call<T>(method: string, path: string, body?: unknown, form?: FormData): Promise<T> {
    const headers: Record<string, string> = { Authorization: `tma ${this.initData()}` };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    let res: Response;
    try {
      res = await fetch(`${this.base}${path}`, {
        method,
        headers,
        body: form ?? (body === undefined ? undefined : JSON.stringify(body)),
      });
    } catch {
      throw new OwnerApiError(0, MSG.network);
    }
    let data: unknown = null;
    try {
      data = await res.json();
    } catch {
      // empty or non-JSON body
    }
    if (!res.ok) throw parseOwnerError(res.status, data);
    return data as T;
  }

  me() {
    return this.call<Awaited<ReturnType<OwnerApi['me']>>>('GET', '/me');
  }
  directions() {
    return this.call<Awaited<ReturnType<OwnerApi['directions']>>>('GET', '/directions');
  }
  events(filter: Parameters<OwnerApi['events']>[0]) {
    return this.call<Awaited<ReturnType<OwnerApi['events']>>>('GET', `/events?filter=${filter}`);
  }
  event(id: string) {
    return this.call<OwnerEvent>('GET', `/events/${id}`);
  }
  createEvent(input: OwnerEventInput) {
    return this.call<OwnerEvent>('POST', '/events', input);
  }
  updateEvent(id: string, patch: OwnerEventPatch) {
    return this.call<OwnerEvent>('PATCH', `/events/${id}`, patch);
  }
  publish(id: string) {
    return this.call<OwnerEvent>('POST', `/events/${id}/publish`);
  }
  unpublish(id: string) {
    return this.call<OwnerEvent>('POST', `/events/${id}/unpublish`);
  }
  uploadPoster(id: string, file: File, focus: Focus) {
    const form = new FormData();
    form.append('file', file);
    form.append('focus_x', String(focus.x));
    form.append('focus_y', String(focus.y));
    return this.call<OwnerEvent>('POST', `/events/${id}/poster`, undefined, form);
  }
  setPosterFocus(id: string, focus: Focus) {
    return this.call<OwnerEvent>('PATCH', `/events/${id}/poster-focus`, { focusX: focus.x, focusY: focus.y });
  }
}
