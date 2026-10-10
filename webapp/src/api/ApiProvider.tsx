import { createContext, useContext, type ReactNode } from 'react';
import type { AppApi } from './AppApi';
import { MockApi, scenarioFromUrl } from './mock/MockApi';

const ApiContext = createContext<AppApi | null>(null);

let defaultApi: AppApi | null = null;

/** Stage A always talks to the in-memory mock; stage B swaps in the HTTP client here. */
function getDefaultApi(): AppApi {
  defaultApi ??= new MockApi({ scenario: scenarioFromUrl() });
  return defaultApi;
}

export function ApiProvider({ api, children }: { api?: AppApi; children: ReactNode }) {
  return <ApiContext.Provider value={api ?? getDefaultApi()}>{children}</ApiContext.Provider>;
}

export function useApi(): AppApi {
  return useContext(ApiContext) ?? getDefaultApi();
}

/** The mock's bank-page controls, or null when a real API is wired in. */
export function useMockApi(): MockApi | null {
  const api = useApi();
  return api instanceof MockApi ? api : null;
}
