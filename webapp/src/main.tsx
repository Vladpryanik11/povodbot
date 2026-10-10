import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import { App } from './App';
import { tg } from './telegram/tg';
import './styles/tokens.css';
import './styles/global.css';

tg.ready();
tg.expand();
tg.disableVerticalSwipes();

// Weak phones lag on backdrop blur; glass then becomes an opaque surface with the same contrast.
const device = navigator as Navigator & { deviceMemory?: number };
if ((device.hardwareConcurrency ?? 8) <= 4 || (device.deviceMemory ?? 8) <= 3) {
  document.documentElement.classList.add('no-blur');
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <HashRouter>
      <App />
    </HashRouter>
  </StrictMode>,
);
