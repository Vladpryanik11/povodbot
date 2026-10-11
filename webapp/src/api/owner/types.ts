import type { Poster } from '../types';

// Field for field with src/api/owner/schemas.py and router.py (camelCase JSON).

export type EventStatus = 'draft' | 'published' | 'cancelled' | 'completed';
export type OwnerFilter = 'all' | 'draft' | 'past';

/** 0–1 point the owner tapped on the photo. */
export interface Focus {
  x: number;
  y: number;
}

export interface OwnerMe {
  role: string;
  permissions: string[];
}

export interface OwnerDirection {
  id: string;
  name: string;
}

export interface OwnerTicketType {
  id: string;
  name: string;
  priceKopecks: number;
  currency: string;
  limit: number;
  active: boolean;
}

export interface OwnerEventListItem {
  id: string;
  title: string;
  startsAt: string;
  status: EventStatus;
  capacity: number;
  sold: number;
  poster: Poster | null;
}

export interface OwnerEvent {
  id: string;
  title: string;
  description: string;
  directionId: string;
  startsAt: string;
  endsAt: string;
  timezone: string;
  address: string | null;
  mapUrl: string | null;
  capacity: number;
  ticketTypes: OwnerTicketType[];
  status: EventStatus;
  publishedAt: string | null;
  createdAt: string;
  /** Opaque edit version: never parse or compare, only send back in PATCH. */
  updatedAt: string;
  accentColor: string | null;
  poster: Poster | null;
  sold: number;
}

export interface OwnerTicketTypeInput {
  id?: string;
  name: string;
  priceKopecks: number;
  limit: number;
  currency?: 'RUB';
  active?: boolean;
}

export interface OwnerEventInput {
  title: string;
  description: string;
  directionId: string;
  startsAt: string;
  endsAt: string;
  timezone: string;
  address: string | null;
  capacity: number;
  mapUrl: string | null;
  accentColor: string | null;
  ticketTypes: OwnerTicketTypeInput[];
}

export type OwnerEventPatch = Partial<OwnerEventInput> & { updatedAt: string };
