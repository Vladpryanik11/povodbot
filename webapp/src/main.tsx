import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { tg } from './telegram/tg';
import './styles/tokens.css';
import './styles/global.css';

tg.ready();
tg.expand();
tg.disableVerticalSwipes();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
