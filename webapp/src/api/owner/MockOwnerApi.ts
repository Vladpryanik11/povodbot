import { MSG } from './messages';
import { OwnerApiError, type OwnerApi } from './OwnerApi';
import { buildOwnerFixtures, type OwnerFixtures } from './ownerFixtures';
import type {
  Focus,
  OwnerDirection,
  OwnerEvent,
  OwnerEventInput,
  OwnerEventListItem,
  OwnerEventPatch,
  OwnerFilter,
  OwnerMe,
  OwnerTicketType,
  OwnerTicketTypeInput,
} from './types';

export type OwnerRole = 'owner' | 'entrance' | 'guest';

/** `?owner=guest|entrance` shows the app to someone without the right; anything else is the owner. */
export function ownerRoleFromUrl(search: string = typeof window === 'undefined' ? '' : window.location.search): OwnerRole {
  const value = new URLSearchParams(search).get('owner');
  return value === 'guest' || value === 'entrance' ? value : 'owner';
}

export const MAX_PHOTO_BYTES = 15 * 1024 * 1024;
export const PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif'];
// Some phones hand over HEIC with no type at all; the server goes by the bytes, so the mock goes by the name.
const PHOTO_NAME = /\.(jpe?g|png|webp|heic|heif)$/i;

const OWNER_PERMISSIONS = [
  'checkin_tickets',
  'lookup_tickets',
  'manage_campaigns',
  'manage_crm',
  'manage_events',
  'manage_orders',
  'manage_roles',
  'refund_orders',
  'view_dashboard',
];
const ENTRANCE_PERMISSIONS = ['checkin_tickets', 'lookup_tickets'];
const CLEARABLE = new Set(['address', 'mapUrl', 'accentColor']);
const MAX_INT = 2147483647;

interface MockOwnerApiOptions {
  role?: OwnerRole;
  now?: () => number;
  latencyMs?: number;
  offline?: boolean;
  fixtures?: OwnerFixtures;
}

const fieldError = (field: string, message: string) => new OwnerApiError(422, message, field);
const rejected = () => new OwnerApiError(422, MSG.rejected);

const isCount = (value: unknown, min: number, max: number) =>
  typeof value === 'number' && Number.isInteger(value) && value >= min && value <= max;

/** `validate` from src/services/events/service.py: same order, same fields, same texts. */
function validate(input: OwnerEventInput): void {
  if (!input.title.trim()) throw fieldError('title', MSG.title);
  if (!input.description.trim()) throw fieldError('description', MSG.description);
  if (input.address !== null && !input.address.trim()) throw fieldError('address', MSG.address);
  if (!isCount(input.capacity, 1, MAX_INT)) throw fieldError('capacity', MSG.capacity);
  const starts = Date.parse(input.startsAt);
  const ends = Date.parse(input.endsAt);
  if (Number.isNaN(starts)) throw fieldError('startsAt', MSG.dateTime);
  if (Number.isNaN(ends)) throw fieldError('endsAt', MSG.dateTime);
  if (ends <= starts) throw fieldError('endsAt', MSG.endsBeforeStart);
  if (input.mapUrl !== null && !isMapUrl(input.mapUrl)) throw fieldError('mapUrl', MSG.mapUrl);
  if (input.accentColor !== null && !/^#[0-9A-Fa-f]{6}$/.test(input.accentColor)) {
    throw fieldError('accentColor', MSG.accentColor);
  }
  for (const t of input.ticketTypes) {
    if (!t.name.trim()) throw fieldError('ticketTypes', MSG.ticketName);
    if (!isCount(t.priceKopecks, 0, Number.MAX_SAFE_INTEGER)) throw fieldError('ticketTypes', MSG.ticketPrice);
    const active = t.active ?? true;
    if (!isCount(t.limit, 1, active ? input.capacity : MAX_INT)) throw fieldError('ticketTypes', MSG.ticketLimit);
  }
}

function isMapUrl(text: string): boolean {
  try {
    const url = new URL(text);
    return (url.protocol === 'https:' || url.protocol === 'http:') && !!url.hostname && !url.username && !url.password;
  } catch {
    return false;
  }
}

function publicationRequirements(event: OwnerEvent): void {
  if (!event.ticketTypes.some((t) => t.active)) throw fieldError('ticketTypes', MSG.needTicket);
  if (!event.poster) throw fieldError('poster', MSG.needPoster);
}

function inputOf(event: OwnerEvent): OwnerEventInput {
  return {
    title: event.title,
    description: event.description,
    directionId: event.directionId,
    startsAt: event.startsAt,
    endsAt: event.endsAt,
    timezone: event.timezone,
    address: event.address,
    capacity: event.capacity,
    mapUrl: event.mapUrl,
    accentColor: event.accentColor,
    ticketTypes: event.ticketTypes.map((t) => ({
      id: t.id,
      name: t.name,
      priceKopecks: t.priceKopecks,
      limit: t.limit,
      active: t.active,
    })),
  };
}

const roundFocus = (v: number) => Math.round(v * 1000) / 1000;

/** In-memory /api/owner with the server's rules (spec section 4) and its texts (MSG). */
export class MockOwnerApi implements OwnerApi {
  readonly role: OwnerRole;
  private readonly now: () => number;
  private readonly latencyMs: number;
  private readonly offline: boolean;
  private readonly data: OwnerFixtures;
  private seq = 0;
  private version = 0;
  private uploading = false;

  constructor(options: MockOwnerApiOptions = {}) {
    this.role = options.role ?? 'owner';
    this.now = options.now ?? Date.now;
    this.latencyMs = options.latencyMs ?? 300;
    this.offline = options.offline ?? false;
    this.data = options.fixtures ?? buildOwnerFixtures(this.now());
    for (const event of this.data.events) event.updatedAt = this.stamp();
  }

  me(): Promise<OwnerMe> {
    return this.call(
      () => ({ role: 'owner', permissions: [...OWNER_PERMISSIONS] }),
      () => ({ role: 'entrance', permissions: [...ENTRANCE_PERMISSIONS] }),
    );
  }

  directions(): Promise<OwnerDirection[]> {
    return this.call(() => structuredClone(this.data.directions));
  }

  events(filter: OwnerFilter): Promise<OwnerEventListItem[]> {
    return this.call(() => {
      const now = this.now();
      const ends = (e: OwnerEvent) => Date.parse(e.endsAt);
      const starts = (e: OwnerEvent) => Date.parse(e.startsAt);
      const list =
        filter === 'past'
          ? this.data.events.filter((e) => e.status !== 'cancelled' && ends(e) < now).sort((a, b) => starts(b) - starts(a))
          : this.data.events
              .filter((e) => (filter === 'draft' ? e.status === 'draft' : e.status === 'draft' || e.status === 'published'))
              .filter((e) => ends(e) >= now)
              .sort((a, b) => starts(a) - starts(b));
      return list.map((e) =>
        structuredClone({
          id: e.id,
          title: e.title,
          startsAt: e.startsAt,
          status: e.status,
          capacity: e.capacity,
          sold: e.sold,
          poster: e.poster,
        }),
      );
    });
  }

  event(id: string): Promise<OwnerEvent> {
    return this.call(() => structuredClone(this.find(id)));
  }

  createEvent(input: OwnerEventInput): Promise<OwnerEvent> {
    return this.call(() => {
      if (input.ticketTypes.some((t) => t.id !== undefined)) throw rejected();
      validate(input);
      this.seq += 1;
      const stamp = this.stamp();
      const event: OwnerEvent = {
        ...structuredClone(input),
        id: `e-new-${this.seq}`,
        ticketTypes: input.ticketTypes.map((t) => this.newTicket(t)),
        status: 'draft',
        publishedAt: null,
        createdAt: new Date(this.now()).toISOString(),
        updatedAt: stamp,
        poster: null,
        sold: 0,
      };
      this.data.events.push(event);
      return structuredClone(event);
    });
  }

  updateEvent(id: string, patch: OwnerEventPatch): Promise<OwnerEvent> {
    return this.call(() => {
      const event = this.find(id);
      if (patch.updatedAt !== event.updatedAt) throw new OwnerApiError(409, MSG.conflict);
      this.requireEditable(event);
      const { updatedAt: _version, ...changes } = patch;
      const candidate: OwnerEventInput = inputOf(event);
      for (const [key, value] of Object.entries(changes)) {
        if (value === undefined) continue;
        if (value === null && !CLEARABLE.has(key)) throw rejected();
        (candidate as unknown as Record<string, unknown>)[key] = value;
      }
      validate(candidate);
      const ids = (changes.ticketTypes ?? []).flatMap((t) => (t.id === undefined ? [] : [t.id]));
      if (new Set(ids).size !== ids.length || ids.some((tid) => !event.ticketTypes.some((t) => t.id === tid))) {
        throw rejected();
      }
      const ticketTypes = changes.ticketTypes ? this.merged(event, candidate) : event.ticketTypes;
      if (event.status === 'published') publicationRequirements({ ...event, ticketTypes });
      if (candidate.capacity < event.sold) throw fieldError('capacity', MSG.capacityBelowSold);

      Object.assign(event, { ...candidate, ticketTypes, updatedAt: this.stamp() });
      return structuredClone(event);
    });
  }

  publish(id: string): Promise<OwnerEvent> {
    return this.call(() => {
      const event = this.find(id);
      if (event.status !== 'draft') throw rejected();
      validate(inputOf(event));
      if (Date.parse(event.startsAt) <= this.now()) throw fieldError('startsAt', MSG.started);
      publicationRequirements(event);
      Object.assign(event, {
        status: 'published',
        publishedAt: new Date(this.now()).toISOString(),
        updatedAt: this.stamp(),
      });
      return structuredClone(event);
    });
  }

  unpublish(id: string): Promise<OwnerEvent> {
    return this.call(() => {
      const event = this.find(id);
      if (event.status !== 'published') throw rejected();
      if (event.sold > 0) throw new OwnerApiError(409, MSG.hasOrders);
      Object.assign(event, { status: 'draft', publishedAt: null, updatedAt: this.stamp() });
      return structuredClone(event);
    });
  }

  async uploadPoster(id: string, file: File, focus: Focus): Promise<OwnerEvent> {
    // Like the server's per-admin lock: a second upload while one is running is turned away.
    const busy = this.uploading;
    this.uploading = true;
    try {
      return await this.call(() => {
        if (busy) throw new OwnerApiError(429, MSG.uploadBusy);
        // The server's order: cheap checks first, then the bytes.
        this.checkFocus(focus);
        const event = this.find(id);
        this.requireEditable(event);
        if (file.size > MAX_PHOTO_BYTES) throw new OwnerApiError(413, MSG.photoTooBig, 'poster');
        const typed = file.type ? PHOTO_TYPES.includes(file.type) : PHOTO_NAME.test(file.name);
        if (!typed) throw new OwnerApiError(415, MSG.notAPhoto, 'poster');
        event.poster = {
          url: URL.createObjectURL(file),
          focusX: roundFocus(focus.x),
          focusY: roundFocus(focus.y),
          width: 1080,
          height: 1350,
        };
        event.updatedAt = this.stamp();
        return structuredClone(event);
      });
    } finally {
      if (!busy) this.uploading = false;
    }
  }

  setPosterFocus(id: string, focus: Focus): Promise<OwnerEvent> {
    return this.call(() => {
      this.checkFocus(focus);
      const event = this.find(id);
      this.requireEditable(event);
      if (event.poster) event.poster = { ...event.poster, focusX: roundFocus(focus.x), focusY: roundFocus(focus.y) };
      event.updatedAt = this.stamp();
      return structuredClone(event);
    });
  }

  /** `entrance` is the door staff's role: it may ask who it is, nothing more. */
  private async call<T>(fn: () => T, asEntrance?: () => T): Promise<T> {
    if (this.latencyMs > 0) await new Promise((resolve) => setTimeout(resolve, this.latencyMs));
    if (this.offline) throw new OwnerApiError(0, MSG.network);
    if (this.role === 'guest') throw new OwnerApiError(403, MSG.noAccess);
    if (this.role === 'entrance') {
      if (!asEntrance) throw new OwnerApiError(403, MSG.noAccess);
      return asEntrance();
    }
    return fn();
  }

  /** A fresh opaque version on every change, unique even when the clock stands still. */
  private stamp(): string {
    this.version += 1;
    return `${new Date(this.now()).toISOString().slice(0, 23)}${String(this.version).padStart(3, '0')}+00:00`;
  }

  private find(id: string): OwnerEvent {
    const event = this.data.events.find((e) => e.id === id);
    if (!event) throw new OwnerApiError(404, MSG.notFound);
    return event;
  }

  private requireEditable(event: OwnerEvent): void {
    if (event.status === 'cancelled' || event.status === 'completed') throw rejected();
  }

  private checkFocus(focus: Focus): void {
    for (const v of [focus.x, focus.y]) {
      if (typeof v !== 'number' || !(v >= 0 && v <= 1)) throw fieldError('focus', MSG.focus);
    }
  }

  private newTicket(t: OwnerTicketTypeInput): OwnerTicketType {
    this.seq += 1;
    return {
      id: `t-new-${this.seq}`,
      name: t.name,
      priceKopecks: t.priceKopecks,
      currency: t.currency ?? 'RUB',
      limit: t.limit,
      active: t.active ?? true,
    };
  }

  /** Saved rows missing from the list are switched off, rows without an id are new. */
  private merged(event: OwnerEvent, candidate: OwnerEventInput): OwnerTicketType[] {
    const rows = candidate.ticketTypes;
    const kept = event.ticketTypes.map((saved) => {
      const row = rows.find((r) => r.id === saved.id);
      if (!row) return { ...saved, active: false };
      return { ...saved, name: row.name, priceKopecks: row.priceKopecks, limit: row.limit, active: row.active ?? true };
    });
    const added = rows.filter((r) => r.id === undefined).map((r) => this.newTicket(r));
    return [...kept, ...added];
  }
}
