import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { posterColor } from '../lib/posterColor';
import { createTg, mainButtonStore } from '../telegram/tg';
import { TgProvider } from '../telegram/hooks';
import { Button } from './Button';
import { AttendeesStack } from './AttendeesStack';
import { DateStrip } from './DateStrip';
import { Dialog } from './Dialog';
import { FilterChips } from './FilterChips';
import { Glow, GlowProvider, useGlow } from './Glow';
import { BottomBar } from './BottomBar';
import { Poster } from './Poster';
import { StatusPill } from './StatusPill';
import { Stepper } from './Stepper';
import { TabBar } from './TabBar';
import { pickTodayTicket } from './TodayPill';
import type { Ticket } from '../api/types';

describe('Stepper', () => {
  it('names the action and the count for screen readers', () => {
    render(<Stepper value={2} max={5} label="Входной" onChange={() => undefined} />);
    expect(screen.getByRole('button', { name: 'Входной: 2 билета. Убавить' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Входной: 2 билета. Добавить' })).toBeInTheDocument();
  });

  it('stops at the maximum and says so', () => {
    render(<Stepper value={2} max={2} label="Входной" onChange={() => undefined} />);
    expect(screen.getByRole('button', { name: /Добавить/ })).toBeDisabled();
    expect(screen.getByText('Больше нет')).toBeInTheDocument();
  });

  it('stops at zero and reports increments', async () => {
    const onChange = vi.fn();
    render(<Stepper value={0} max={3} label="Входной" onChange={onChange} />);
    expect(screen.getByRole('button', { name: /Убавить/ })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: /Добавить/ }));
    expect(onChange).toHaveBeenCalledWith(1);
  });
});

describe('Poster', () => {
  it('falls back to a coloured block with the direction icon when there is no photo', () => {
    render(<Poster poster={null} title="Настолки до утра" ratio="4:5" icon="book" />);
    const block = screen.getByTestId('poster');
    expect(block.style.backgroundColor).toBe(hexToRgb(posterColor('Настолки до утра')));
    expect(block.querySelector('img')).toBeNull();
    expect(block.querySelector('svg')).not.toBeNull();
  });

  it('shows the photo at the focus point under a scrim', () => {
    render(
      <Poster
        poster={{ url: './mock/kino.jpg', width: 800, height: 1000, focusX: 0.3, focusY: 0.4 }}
        title="Повод для киновечера"
        ratio="2:1"
        icon="film"
      />,
    );
    const img = screen.getByTestId('poster').querySelector('img')!;
    expect(img).not.toBeNull();
    expect(img.style.objectPosition).toBe('30% 40%');
    expect(screen.getByTestId('scrim')).toBeInTheDocument();
  });

  it('treats a photo with a short side under 600 px as missing', () => {
    render(
      <Poster
        poster={{ url: './mock/tiny.jpg', width: 400, height: 500, focusX: 0.5, focusY: 0.5 }}
        title="Кино"
        ratio="4:5"
        icon="film"
      />,
    );
    expect(screen.getByTestId('poster').querySelector('img')).toBeNull();
  });
});

describe('Button', () => {
  it('keeps its label in place while loading so the width does not jump', () => {
    render(<Button loading>Оплатить 3 100 ₽</Button>);
    const button = screen.getByRole('button');
    expect(button).toHaveAttribute('aria-busy', 'true');
    expect(button).toHaveTextContent('Оплатить 3 100 ₽');
  });
});

describe('BottomBar', () => {
  it('draws the page bottom bar with the summary and a white button, even inside Telegram', async () => {
    const web = { colorScheme: 'dark', initDataUnsafe: {}, MainButton: {} } as unknown as Parameters<typeof createTg>[0];
    const onClick = vi.fn();
    render(
      <TgProvider value={createTg(web)}>
        <BottomBar />
      </TgProvider>,
    );
    expect(screen.queryByRole('button')).toBeNull();
    act(() => mainButtonStore.set({ text: 'Купить', enabled: true, progress: false, summary: '2 билета · 3 100 ₽', onClick }));
    expect(screen.getByText('2 билета · 3 100 ₽')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Купить' }));
    expect(onClick).toHaveBeenCalledTimes(1);
    act(() => mainButtonStore.set({ text: 'Мест нет', enabled: false, progress: false, onClick }));
    expect(screen.getByRole('button', { name: 'Мест нет' })).toBeDisabled();
    act(() => mainButtonStore.set({ text: 'Купить', enabled: true, progress: true, onClick }));
    expect(screen.getByRole('button', { name: 'Купить' })).toHaveAttribute('aria-busy', 'true');
    act(() => mainButtonStore.set(null));
    expect(screen.queryByRole('button')).toBeNull();
  });
});

describe('pickTodayTicket', () => {
  const NOW = Date.parse('2026-10-10T09:00:00Z'); // 12:00 in Moscow
  const ticket = (over: Partial<Ticket>): Ticket => ({
    id: 'tk',
    eventId: 'e',
    eventTitle: 'Амели',
    startsAt: '2026-10-10T20:00:00Z', // 23:00 Moscow, today
    timezone: 'Europe/Moscow',
    address: null,
    mapUrl: null,
    typeName: 'Стандарт',
    position: 1,
    ofCount: 1,
    shortCode: '4821',
    status: 'valid',
    qrToken: 'pv1.tk',
    poster: null,
    ...over,
  });

  it('picks a valid ticket for an evening today', () => {
    const t = ticket({ id: 'today' });
    expect(pickTodayTicket([ticket({ id: 'later', startsAt: '2026-10-12T16:00:00Z' }), t], NOW)).toBe(t);
  });

  it('skips a ticket already used today', () => {
    expect(pickTodayTicket([ticket({ status: 'used', qrToken: null })], NOW)).toBeNull();
  });

  it('skips an evening today that started more than 6 hours ago', () => {
    expect(pickTodayTicket([ticket({ startsAt: '2026-10-10T02:00:00Z' })], NOW)).toBeNull();
  });

  it('skips an evening tomorrow', () => {
    expect(pickTodayTicket([ticket({ startsAt: '2026-10-11T16:00:00Z' })], NOW)).toBeNull();
  });
});

describe('TabBar', () => {
  it('tab bar: three icon tabs, active one filled white', () => {
    render(
      <MemoryRouter initialEntries={['/favorites']}>
        <TabBar hidden={false} />
      </MemoryRouter>,
    );
    const nav = screen.getByRole('navigation', { name: 'Разделы' });
    expect(nav.querySelectorAll('a')).toHaveLength(3);
    const home = screen.getByRole('link', { name: 'Дом' });
    const fav = screen.getByRole('link', { name: 'Избранное' });
    expect(home).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: 'Кабинет' })).toHaveAttribute('href', '/me');
    expect(fav).toHaveAttribute('aria-current', 'page');
    expect(fav.querySelector('svg')).toHaveAttribute('fill', 'currentColor');
    expect(home.querySelector('svg')).toHaveAttribute('fill', 'none');
    expect(home).not.toHaveAttribute('aria-current');
    expect(screen.queryByText('Дом')).toBeNull();
  });

  it('gives a selection haptic on tap', async () => {
    const tg = createTg();
    const selection = vi.spyOn(tg.haptic, 'selection');
    render(
      <TgProvider value={tg}>
        <MemoryRouter initialEntries={['/']}>
          <TabBar hidden={false} />
        </MemoryRouter>
      </TgProvider>,
    );
    await userEvent.click(screen.getByRole('link', { name: 'Кабинет' }));
    expect(selection).toHaveBeenCalled();
  });
});

describe('Dialog', () => {
  it('confirms and cancels', async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <Dialog
        title="Отменить бронь?"
        text="Места вернутся в продажу."
        confirmLabel="Отменить"
        cancelLabel="Оставить"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    expect(screen.getByRole('dialog', { name: 'Отменить бронь?' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Оставить' }));
    await userEvent.click(screen.getByRole('button', { name: 'Отменить' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});

function hexToRgb(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`;
}

describe('Glow', () => {
  it('glow takes the colour of the mounted screen and clears on unmount', () => {
    function Painted() {
      useGlow('#D4537E');
      return null;
    }
    const view = render(
      <GlowProvider>
        <Glow />
        <Painted />
      </GlowProvider>,
    );
    const glow = view.container.querySelector('[data-glow]')!;
    expect(document.documentElement.style.getPropertyValue('--poster')).toBe('#D4537E');
    expect(glow).not.toHaveAttribute('data-off');

    view.rerender(
      <GlowProvider>
        <Glow />
      </GlowProvider>,
    );
    expect(document.documentElement.style.getPropertyValue('--poster')).toBe('');
    expect(view.container.querySelector('[data-glow]')).toHaveAttribute('data-off');
  });
});

describe('StatusPill', () => {
  it('says today, seats left or sold out; the dot only where there is a colour to show', () => {
    const { container, rerender } = render(<StatusPill kind="today" />);
    expect(screen.getByText('Сегодня')).toBeInTheDocument();
    expect(container.querySelector('[data-dot]')).not.toBeNull();
    rerender(<StatusPill kind="left" count={12} />);
    expect(screen.getByText('Осталось 12')).toBeInTheDocument();
    rerender(<StatusPill kind="soldout" />);
    expect(screen.getByText('Мест нет')).toBeInTheDocument();
    expect(container.querySelector('[data-dot]')).toBeNull();
  });
});

describe('AttendeesStack', () => {
  it('shows up to three faces and counts the rest', () => {
    render(<AttendeesStack count={23} avatars={['/a.svg', '/b.svg', '/c.svg']} />);
    expect(screen.getByText('+20')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Идут 23 человека' })).toBeInTheDocument();
  });

  it('renders nothing when nobody is going', () => {
    const { container } = render(<AttendeesStack count={0} avatars={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('FilterChips', () => {
  const items = [
    { id: 'd-film', title: 'Киновечер' },
    { id: 'd-workshop', title: 'Мастерклассы' },
  ];

  it('picks a direction and «Все» resets it', async () => {
    const onChange = vi.fn();
    render(<FilterChips items={items} value="d-film" onChange={onChange} />);
    expect(screen.getByRole('radiogroup')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Киновечер' })).toHaveAttribute('aria-checked', 'true');
    await userEvent.click(screen.getByRole('radio', { name: 'Мастерклассы' }));
    expect(onChange).toHaveBeenLastCalledWith('d-workshop');
    await userEvent.click(screen.getByRole('radio', { name: 'Все' }));
    expect(onChange).toHaveBeenLastCalledWith(null);
  });
});

describe('DateStrip', () => {
  const from = Date.parse('2026-10-10T09:00:00Z');

  it('marks days with events and a second tap on the chosen day clears it', async () => {
    const onChange = vi.fn();
    const { container } = render(
      <DateStrip from={from} days={14} marked={new Set(['2026-10-12'])} value="2026-10-12" onChange={onChange} />,
    );
    expect(screen.getAllByRole('button')).toHaveLength(14);
    expect(container.querySelectorAll('[data-marked]')).toHaveLength(1);
    const monday = screen.getByRole('button', { name: 'пн 12' });
    expect(monday).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(monday);
    expect(onChange).toHaveBeenLastCalledWith(null);
    await userEvent.click(screen.getByRole('button', { name: 'вт 13' }));
    expect(onChange).toHaveBeenLastCalledWith('2026-10-13');
  });
});
