import type { Me } from './api/types';

/** Phone-side copy of the live order id (CloudStorage in Telegram), in case the server forgets it. */
export const ACTIVE_ORDER_KEY = 'activeOrderId';

/** Telegram opens the app with '#tgWebAppData=…'; anything that is not an app route becomes '#/'. */
export function normalizeLaunchHash(hash: string): string | null {
  return hash.startsWith('#/') ? null : '#/';
}

const ROUTES: Record<string, (id: string) => string> = {
  event: (id) => `/events/${id}`,
  order: (id) => `/order/${id}`,
  ticket: (id) => `/tickets/${id}`,
  claim: (token) => `/claim/${token}`,
  vote: () => '/polls',
};

/** Where the app opens: a live reservation always wins over the link the guest came by. */
export function resolveStart(startParam: string | null, me: Me): string {
  if (me.activeOrder) return `/order/${me.activeOrder.id}`;
  const match = /^([a-z]+)_([A-Za-z0-9-]+)$/.exec(startParam ?? '');
  if (!match) return '/';
  const route = ROUTES[match[1]];
  return route ? route(match[2]) : '/';
}
