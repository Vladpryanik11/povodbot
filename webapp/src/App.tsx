import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { StartGate } from './StartGate';
import { Afisha } from './screens/Afisha';
import { EventScreen } from './screens/EventScreen';
import { MockPay } from './screens/MockPay';
import { OrderScreen } from './screens/OrderScreen';
import { ClaimScreen } from './screens/ClaimScreen';
import { Polls } from './screens/Polls';
import { Tickets } from './screens/Tickets';
import { TicketScreen } from './screens/TicketScreen';
import { useMainButtonState, useTheme } from './telegram/hooks';
import { Glow, GlowProvider } from './ui/Glow';
import { InPageMainButton } from './ui/InPageMainButton';
import { TabBar } from './ui/TabBar';
import styles from './App.module.css';

const TAB_PATHS = new Set(['/', '/tickets', '/polls']);

export function App() {
  useTheme();
  const { pathname } = useLocation();
  const mainButton = useMainButtonState();

  return (
    <GlowProvider>
      <StartGate>
        <div className={styles.app}>
          <Glow />
          <Routes>
            <Route path="/" element={<Afisha />} />
            <Route path="/events/:id" element={<EventScreen />} />
            <Route path="/order/:id" element={<OrderScreen />} />
            <Route path="/mock-pay/:id" element={<MockPay />} />
            <Route path="/tickets" element={<Tickets />} />
            <Route path="/tickets/:id" element={<TicketScreen />} />
            <Route path="/claim/:token" element={<ClaimScreen />} />
            <Route path="/polls" element={<Polls />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
        <TabBar hidden={!TAB_PATHS.has(pathname) || mainButton !== null} />
      </StartGate>
      <InPageMainButton />
    </GlowProvider>
  );
}
