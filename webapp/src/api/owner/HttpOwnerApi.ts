import { ownerCall, type OwnerCall } from './http';
import { parseOwnerError, type OwnerApi } from './OwnerApi';
import type { Focus, OwnerEvent, OwnerEventInput, OwnerEventPatch } from './types';

/** Real /api/owner client. Same origin as the Mini App (Caddy), signed in with Telegram initData. */
export class HttpOwnerApi implements OwnerApi {
  private readonly call: OwnerCall;

  constructor(initData: () => string, base = '/api/owner') {
    this.call = ownerCall(initData, base, parseOwnerError);
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
