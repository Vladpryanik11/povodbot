import { MSG } from '../api/owner/messages';
import type { OwnerEvent, OwnerEventInput, OwnerTicketTypeInput } from '../api/owner/types';
import type { EventDetail, TicketTypeOffer } from '../api/types';

export const CLUB_TIMEZONE = 'Europe/Moscow';

export interface TicketRow {
  /** Stable React key; a saved row's key is its id. */
  key: string;
  id: string | null;
  name: string;
  price: string;
  limit: string;
  active: boolean;
}

/** What the owner typed, as typed: every value is a string except the marked ones. */
export interface EventForm {
  title: string;
  description: string;
  directionId: string;
  /** 'YYYY-MM-DDTHH:mm' wall time in `timezone`, '' when not set. */
  startsLocal: string;
  endsLocal: string;
  timezone: string;
  venueTbd: boolean;
  address: string;
  mapUrl: string;
  capacity: string;
  /** '' = none. */
  accentColor: string;
  tickets: TicketRow[];
}

export const FORM_FIELDS = [
  'title',
  'description',
  'directionId',
  'startsAt',
  'endsAt',
  'address',
  'mapUrl',
  'capacity',
  'accentColor',
  'ticketTypes',
  'poster',
] as const;
export type FormField = (typeof FORM_FIELDS)[number];

// --- time zones ---

/** Wall time of `instant` in `timeZone`, read as if it were UTC, minus the instant: the zone's offset in ms. */
function zoneOffsetMs(instant: number, timeZone: string): number {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone,
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).formatToParts(instant);
  const get = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find((p) => p.type === type)?.value);
  const wall = Date.UTC(get('year'), get('month') - 1, get('day'), get('hour'), get('minute'), get('second'));
  return wall - Math.floor(instant / 1000) * 1000;
}

const pad2 = (n: number) => String(n).padStart(2, '0');

/** '2026-10-20T19:00' in `timeZone` → '2026-10-20T19:00:00+03:00'. */
export function toZonedIso(local: string, timeZone: string): string {
  const wall = `${local.slice(0, 16)}:00`;
  const asUtc = Date.parse(`${wall}Z`);
  // Two passes: the offset at the guessed instant may differ across a DST switch.
  let offset = zoneOffsetMs(asUtc, timeZone);
  offset = zoneOffsetMs(asUtc - offset, timeZone);
  const minutes = Math.round(offset / 60000);
  const sign = minutes < 0 ? '-' : '+';
  const abs = Math.abs(minutes);
  return `${wall}${sign}${pad2(Math.floor(abs / 60))}:${pad2(abs % 60)}`;
}

/** Any ISO 8601 instant → 'YYYY-MM-DDTHH:mm' wall time in `timeZone`. */
export function fromZonedIso(iso: string, timeZone: string): string {
  // The server sends microseconds; keep milliseconds so every engine parses it.
  const instant = Date.parse(iso.replace(/(\.\d{3})\d+/, '$1'));
  const wall = new Date(instant + zoneOffsetMs(instant, timeZone));
  return wall.toISOString().slice(0, 16);
}

// --- numbers ---

const SPACES = /[\s  ]/g;

/** '1 500', '1500,50', '1 500.5' → kopecks; null when it is not a price. */
export function parseRubles(text: string): number | null {
  const match = /^(\d+)(?:[.,](\d{1,2}))?$/.exec(text.replace(SPACES, ''));
  if (!match) return null;
  const kopecks = Number(match[1]) * 100 + Number((match[2] ?? '').padEnd(2, '0'));
  return Number.isSafeInteger(kopecks) ? kopecks : null;
}

export function formatRubles(kopecks: number): string {
  const rest = kopecks % 100;
  const rubles = (kopecks - rest) / 100;
  return rest === 0 ? String(rubles) : `${rubles},${pad2(rest)}`;
}

/** A whole number ≥ 1, or null. */
export function parseCount(text: string): number | null {
  const trimmed = text.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const n = Number(trimmed);
  return n >= 1 && Number.isSafeInteger(n) ? n : null;
}

// --- form ↔ event ---

let rowSeq = 0;

export function newTicketRow(): TicketRow {
  rowSeq += 1;
  return { key: `new-${rowSeq}`, id: null, name: '', price: '', limit: '', active: true };
}

export function emptyForm(): EventForm {
  return {
    title: '',
    description: '',
    directionId: '',
    startsLocal: '',
    endsLocal: '',
    timezone: CLUB_TIMEZONE,
    venueTbd: false,
    address: '',
    mapUrl: '',
    capacity: '',
    accentColor: '',
    tickets: [],
  };
}

export function formFromEvent(event: OwnerEvent): EventForm {
  return {
    title: event.title,
    description: event.description,
    directionId: event.directionId,
    startsLocal: fromZonedIso(event.startsAt, event.timezone),
    endsLocal: fromZonedIso(event.endsAt, event.timezone),
    timezone: event.timezone,
    venueTbd: event.address === null,
    address: event.address ?? '',
    mapUrl: event.mapUrl ?? '',
    capacity: String(event.capacity),
    accentColor: event.accentColor ?? '',
    tickets: event.ticketTypes.map((t) => ({
      key: t.id,
      id: t.id,
      name: t.name,
      price: formatRubles(t.priceKopecks),
      limit: String(t.limit),
      active: t.active,
    })),
  };
}

type ToInput = { ok: true; input: OwnerEventInput } | { ok: false; field: FormField; message: string };

/**
 * Checks only what cannot be sent at all; the rest (empty title, description or address,
 * end before start) is the server's call, and its message lands under the field.
 */
export function formToInput(form: EventForm): ToInput {
  if (!form.directionId) return { ok: false, field: 'directionId', message: MSG.direction };
  if (!form.startsLocal) return { ok: false, field: 'startsAt', message: MSG.dateTime };
  if (!form.endsLocal) return { ok: false, field: 'endsAt', message: MSG.dateTime };
  const capacity = parseCount(form.capacity);
  if (capacity === null) return { ok: false, field: 'capacity', message: MSG.capacity };

  const ticketTypes: OwnerTicketTypeInput[] = [];
  for (const row of form.tickets) {
    const name = row.name.trim();
    if (!name) return { ok: false, field: 'ticketTypes', message: MSG.ticketName };
    const priceKopecks = parseRubles(row.price);
    if (priceKopecks === null) return { ok: false, field: 'ticketTypes', message: MSG.ticketPrice };
    const limit = parseCount(row.limit);
    if (limit === null) return { ok: false, field: 'ticketTypes', message: MSG.ticketLimit };
    ticketTypes.push({
      ...(row.id ? { id: row.id } : {}),
      name,
      priceKopecks,
      limit,
      currency: 'RUB',
      active: row.active,
    });
  }

  return {
    ok: true,
    input: {
      title: form.title.trim(),
      description: form.description.trim(),
      directionId: form.directionId,
      startsAt: toZonedIso(form.startsLocal, form.timezone),
      endsAt: toZonedIso(form.endsLocal, form.timezone),
      timezone: form.timezone,
      address: form.venueTbd ? null : form.address.trim(),
      capacity,
      mapUrl: form.mapUrl.trim() || null,
      accentColor: form.accentColor.trim() || null,
      ticketTypes,
    },
  };
}

/** What is still missing before «Опубликовать», in the words the hint uses. */
export function publishGaps(form: EventForm, hasPoster: boolean): string[] {
  const gaps: string[] = [];
  if (!form.title.trim()) gaps.push('название');
  if (!form.directionId) gaps.push('направление');
  if (!form.startsLocal || !form.endsLocal) gaps.push('дату и время');
  if (!form.venueTbd && !form.address.trim()) gaps.push('адрес');
  if (!form.description.trim()) gaps.push('описание');
  if (parseCount(form.capacity) === null) gaps.push('вместимость');
  if (!form.tickets.some((t) => t.active)) gaps.push('билет');
  if (!hasPoster) gaps.push('фото');
  return gaps;
}

const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;

/** The guest's event screen built from unsaved input; never throws on half-typed values. */
export function toPreviewDetail(form: EventForm, event: OwnerEvent | undefined, now: number): EventDetail {
  const capacity = parseCount(form.capacity) ?? 0;
  const seatsLeft = Math.max(0, capacity - (event?.sold ?? 0));
  const ticketTypes: TicketTypeOffer[] = [];
  for (const row of form.tickets) {
    const priceKopecks = parseRubles(row.price);
    if (!row.active || priceKopecks === null) continue;
    ticketTypes.push({
      id: row.id ?? row.key,
      name: row.name.trim(),
      priceKopecks,
      seatsLeft: Math.min(parseCount(row.limit) ?? 0, seatsLeft),
    });
  }
  const accent = form.accentColor.trim();
  return {
    id: event?.id ?? 'preview',
    title: form.title.trim(),
    startsAt: form.startsLocal ? toZonedIso(form.startsLocal, form.timezone) : new Date(now).toISOString(),
    timezone: form.timezone,
    address: form.venueTbd ? null : form.address.trim() || null,
    poster: event?.poster ?? null,
    minPriceKopecks: ticketTypes.length ? Math.min(...ticketTypes.map((t) => t.priceKopecks)) : 0,
    seatsLeft,
    soldOut: seatsLeft === 0,
    directionId: form.directionId,
    accentColor: HEX_COLOR.test(accent) ? accent : null,
    attendees: { count: 0, avatars: [] },
    description: form.description.trim(),
    mapUrl: form.mapUrl.trim() || null,
    ticketTypes,
    poll: null,
  };
}
