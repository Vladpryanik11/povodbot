import { Route, Routes, useLocation } from 'react-router-dom';
import { StartGate } from './StartGate';
import { Afisha } from './screens/Afisha';
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
            <Route path="/events/:id" element={<Soon title="Мероприятие" />} />
            <Route path="/order/:id" element={<Soon title="Заказ" />} />
            <Route path="/mock-pay/:id" element={<Soon title="Оплата" />} />
            <Route path="/tickets" element={<Soon title="Билеты" />} />
            <Route path="/tickets/:id" element={<Soon title="Билет" />} />
            <Route path="/claim/:token" element={<Soon title="Билет от друга" />} />
            <Route path="/polls" element={<Soon title="Голосуем" />} />
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
