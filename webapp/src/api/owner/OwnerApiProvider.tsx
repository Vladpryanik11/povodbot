import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import { DraftStore } from '../../owner/drafts';
import { scenarioFromUrl } from '../mock/MockApi';
import { MockOwnerApi, ownerRoleFromUrl } from './MockOwnerApi';
import type { OwnerApi } from './OwnerApi';

interface OwnerContext {
  api: OwnerApi;
  drafts: DraftStore;
}

const Context = createContext<OwnerContext | null>(null);

let fallback: OwnerContext | null = null;

/** Stage A always talks to the in-memory mock; stage B swaps in the HTTP client here. */
function getFallback(): OwnerContext {
  fallback ??= {
    api: new MockOwnerApi({ role: ownerRoleFromUrl(), offline: scenarioFromUrl() === 'offline' }),
    drafts: new DraftStore(),
  };
  return fallback;
}

export function OwnerApiProvider({ api, children }: { api?: OwnerApi; children: ReactNode }) {
  const [drafts] = useState(() => new DraftStore());
  const value = useMemo(() => ({ api: api ?? getFallback().api, drafts }), [api, drafts]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useOwnerApi(): OwnerApi {
  return (useContext(Context) ?? getFallback()).api;
}

export function useOwnerDrafts(): DraftStore {
  return (useContext(Context) ?? getFallback()).drafts;
}
