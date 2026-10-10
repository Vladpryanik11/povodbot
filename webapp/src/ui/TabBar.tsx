import { CalendarDays, Ticket, Vote } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import styles from './TabBar.module.css';

const TABS = [
  { to: '/', label: 'Афиша', Icon: CalendarDays, end: true },
  { to: '/tickets', label: 'Билеты', Icon: Ticket, end: false },
  { to: '/polls', label: 'Голосуем', Icon: Vote, end: false },
] as const;

export function TabBar({ hidden }: { hidden: boolean }) {
  return (
    <nav className={`${styles.bar} glass ${hidden ? styles.hidden : ''}`} aria-label="Разделы">
      {TABS.map(({ to, label, Icon, end }) => (
        <NavLink key={to} to={to} end={end} className={({ isActive }) => `${styles.tab} ${isActive ? styles.active : ''}`}>
          {({ isActive }) => (
            <>
              <Icon size={24} strokeWidth={isActive ? 2 : 1.75} aria-hidden="true" />
              <span>{label}</span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}
