import { createContext, useContext, type ReactNode } from 'react';
import type { AppApi } from './AppApi';
import { HttpAppApi } from './HttpAppApi';
import { MockApi, scenarioFromUrl } from './mock/MockApi';

const ApiContext = createContext<AppApi | null>(null);

let defaultApi: AppApi | null = null;

/** Inside Telegram (signed initData present) read the real afisha; in a plain browser use the mock. */
function getDefaultApi(): AppApi {
  defaultApi ??= window.Telegram?.WebApp?.initData ? new HttpAppApi() : new MockApi({ scenario: scenarioFromUrl() });
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
