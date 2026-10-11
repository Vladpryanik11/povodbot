import { MSG } from './messages';
import type {
  Focus,
  OwnerDirection,
  OwnerEvent,
  OwnerEventInput,
  OwnerEventListItem,
  OwnerEventPatch,
  OwnerFilter,
  OwnerMe,
} from './types';

/** `status === 0` means no network. `field` names the form field the message belongs under. */
export class OwnerApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly field: string | null = null,
  ) {
    super(message);
    this.name = 'OwnerApiError';
  }
}

/**
 * Contract of /api/owner (spec section 4). Stage A implements it with MockOwnerApi.
 *
 * me()               GET   /api/owner/me
 * directions()       GET   /api/owner/directions
 * events(filter)     GET   /api/owner/events?filter=all|draft|past
 * event(id)          GET   /api/owner/events/{id}
 * createEvent()      POST  /api/owner/events
 * updateEvent()      PATCH /api/owner/events/{id}             — body carries updatedAt as the version
 * publish(id)        POST  /api/owner/events/{id}/publish
 * unpublish(id)      POST  /api/owner/events/{id}/unpublish
 * uploadPoster()     POST  /api/owner/events/{id}/poster       — multipart, snake_case: file, focus_x, focus_y
 * setPosterFocus()   PATCH /api/owner/events/{id}/poster-focus — JSON {focusX, focusY}
 *
 * Errors reject with OwnerApiError (see parseOwnerError).
 */
export interface OwnerApi {
  me(): Promise<OwnerMe>;
  directions(): Promise<OwnerDirection[]>;
  events(filter: OwnerFilter): Promise<OwnerEventListItem[]>;
  event(id: string): Promise<OwnerEvent>;
  createEvent(input: OwnerEventInput): Promise<OwnerEvent>;
  updateEvent(id: string, patch: OwnerEventPatch): Promise<OwnerEvent>;
  publish(id: string): Promise<OwnerEvent>;
  unpublish(id: string): Promise<OwnerEvent>;
  uploadPoster(id: string, file: File, focus: Focus): Promise<OwnerEvent>;
  setPosterFocus(id: string, focus: Focus): Promise<OwnerEvent>;
}

const DETAIL_BY_STATUS: Record<number, string> = {
  401: MSG.signIn,
  403: MSG.noAccess,
  503: MSG.unavailable,
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

/**
 * The server answers in three shapes: the owner body `{field?, message}` (already Russian),
 * a FastAPI `{detail: string}` (English, by status) and a FastAPI validation `{detail: [{loc}]}`.
 */
export function parseOwnerError(status: number, body: unknown): OwnerApiError {
  if (!isRecord(body)) return new OwnerApiError(status, MSG.unknown);
  if (typeof body.message === 'string') {
    const field = typeof body.field === 'string' ? body.field : null;
    return new OwnerApiError(status, body.message, field);
  }
  const { detail } = body;
  if (typeof detail === 'string') {
    return new OwnerApiError(status, DETAIL_BY_STATUS[status] ?? MSG.unknown);
  }
  if (Array.isArray(detail)) {
    const loc: unknown = isRecord(detail[0]) ? detail[0].loc : null;
    const field =
      Array.isArray(loc) && loc[0] === 'body' && typeof loc[1] === 'string' ? loc[1] : null;
    return new OwnerApiError(status, MSG.checkField, field);
  }
  return new OwnerApiError(status, MSG.unknown);
}
