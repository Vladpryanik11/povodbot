import { NavLink } from 'react-router-dom';
import { useTg } from '../telegram/hooks';
import { HeartIcon, HomeIcon, ProfileIcon } from './icons/NavIcons';
import styles from './TabBar.module.css';

const TABS = [
  { to: '/', label: 'Дом', Icon: HomeIcon, end: true },
  { to: '/favorites', label: 'Избранное', Icon: HeartIcon, end: false },
  { to: '/me', label: 'Кабинет', Icon: ProfileIcon, end: false },
] as const;

/** Floating capsule, icons only; the active tab is filled white (spec v2 §4). */
export function TabBar({ hidden }: { hidden: boolean }) {
  const tg = useTg();
  return (
    <nav className={`${styles.bar} ${hidden ? styles.hidden : ''}`} aria-label="Разделы">
      {TABS.map(({ to, label, Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          aria-label={label}
          onClick={() => tg.haptic.selection()}
          className={({ isActive }) => `${styles.tab} ${isActive ? styles.active : ''}`}
        >
          {({ isActive }) => <Icon filled={isActive} />}
        </NavLink>
      ))}
    </nav>
  );
}
