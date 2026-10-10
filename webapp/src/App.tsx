import { Route, Routes } from 'react-router-dom';
import { useTheme } from './telegram/hooks';
import { Kit } from './screens/Kit';

export function App() {
  useTheme();
  return (
    <Routes>
      {import.meta.env.DEV ? <Route path="/kit" element={<Kit />} /> : null}
      <Route path="*" element={<main />} />
    </Routes>
  );
}
