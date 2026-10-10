import { Route, Routes, useLocation } from 'react-router-dom';
import { StartGate } from './StartGate';
import { Afisha } from './screens/Afisha';
import { EventScreen } from './screens/EventScreen';
import { MockPay } from './screens/MockPay';
import { OrderScreen } from './screens/OrderScreen';
import { ClaimScreen } from './screens/ClaimScreen';
import { Polls } from './screens/Polls';
import { Tickets } from './screens/Tickets';
import { TicketScreen } from './screens/TicketScreen';
import { Kit } from './screens/Kit';
import { useMainButtonState, useTheme } from './telegram/hooks';
import { InPageMainButton } from './ui/InPageMainButton';
import { TabBar } from './ui/TabBar';
import styles from './App.module.css';

const TAB_PATHS = new Set(['/', '/tickets', '/polls']);

function Soon({ title }: { title: string }) {
  return <p className={styles.soon}>{title}</p>;
}

export function App() {
  useTheme();
  const { pathname } = useLocation();
  const mainButton = useMainButtonState();

  return (
    <>
      <StartGate>
        <div className={styles.app}>
          <Routes>
            <Route path="/" element={<Afisha />} />
            <Route path="/events/:id" element={<EventScreen />} />
            <Route path="/order/:id" element={<OrderScreen />} />
            <Route path="/mock-pay/:id" element={<MockPay />} />
            <Route path="/tickets" element={<Tickets />} />
            <Route path="/tickets/:id" element={<TicketScreen />} />
            <Route path="/claim/:token" element={<ClaimScreen />} />
            <Route path="/polls" element={<Polls />} />
            {import.meta.env.DEV ? <Route path="/kit" element={<Kit />} /> : null}
            <Route path="*" element={<Soon title="Такой страницы нет" />} />
          </Routes>
        </div>
        <TabBar hidden={!TAB_PATHS.has(pathname) || mainButton !== null} />
      </StartGate>
      <InPageMainButton />
    </>
  );
}
