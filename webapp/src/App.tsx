import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { StartGate } from './StartGate';
import { EventScreen } from './screens/EventScreen';
import { Favorites } from './screens/Favorites';
import { Home } from './screens/Home';
import { MockPay } from './screens/MockPay';
import { OrderScreen } from './screens/OrderScreen';
import { ClaimScreen } from './screens/ClaimScreen';
import { TicketScreen } from './screens/TicketScreen';
import { useTheme } from './telegram/hooks';
import { Glow, GlowProvider } from './ui/Glow';
import { InPageMainButton } from './ui/InPageMainButton';
import { TabBar } from './ui/TabBar';
import styles from './App.module.css';

export const TAB_PATHS = new Set(['/', '/favorites', '/me']);

export function App() {
  useTheme();
  const { pathname } = useLocation();

  return (
    <GlowProvider>
      <StartGate>
        <div className={styles.app}>
          <Glow />
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/events/:id" element={<EventScreen />} />
            <Route path="/order/:id" element={<OrderScreen />} />
            <Route path="/mock-pay/:id" element={<MockPay />} />
            <Route path="/favorites" element={<Favorites />} />
            <Route path="/me" element={null} />
            <Route path="/tickets" element={<Navigate to="/me" replace />} />
            <Route path="/tickets/:id" element={<TicketScreen />} />
            <Route path="/claim/:token" element={<ClaimScreen />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
        <TabBar hidden={!TAB_PATHS.has(pathname)} />
      </StartGate>
      <InPageMainButton />
    </GlowProvider>
  );
}
