import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import { ApiProvider } from './api/ApiProvider';
import { App } from './App';
import { normalizeLaunchHash } from './start';
import { tg } from './telegram/tg';
import './styles/tokens.css';
import './styles/global.css';

// telegram-web-app.js has already read its launch parameters from the hash by now.
const launchHash = normalizeLaunchHash(window.location.hash);
if (launchHash) window.history.replaceState(null, '', window.location.pathname + window.location.search + launchHash);

tg.ready();
tg.expand();
tg.disableVerticalSwipes();

// Weak phones lag on backdrop blur; glass then becomes an opaque surface with the same contrast.
const device = navigator as Navigator & { deviceMemory?: number };
if ((device.hardwareConcurrency ?? 8) <= 4 || (device.deviceMemory ?? 8) <= 3) {
  document.documentElement.classList.add('no-blur');
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 15_000, refetchOnWindowFocus: false } },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ApiProvider>
        <HashRouter>
          <App />
        </HashRouter>
      </ApiProvider>
    </QueryClientProvider>
  </StrictMode>,
);
