import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { Ticket } from '../api/types';
import { PaperTicket } from './PaperTicket';
import { TicketFan } from './TicketFan';

const ticket = (over: Partial<Ticket> = {}): Ticket => ({
  id: 'tk-1',
  eventId: 'e-film',
  eventTitle: 'Амели на большом экране',
  startsAt: '2026-10-25T20:00:00Z',
  timezone: 'Europe/Moscow',
  address: null,
  mapUrl: null,
  typeName: 'Входной',
  position: 1,
  ofCount: 2,
  shortCode: '4821',
  status: 'valid',
  qrToken: 'pv1.tk-1',
  poster: null,
  ...over,
});

const qr = () => screen.queryByRole('img', { name: 'QR-код билета' });

describe('PaperTicket', () => {
  it('valid: poster, the 2×2 data grid and a stub with the QR', async () => {
    render(<PaperTicket ticket={ticket()} guestName="Аня" />);
    await waitFor(() => expect(qr()?.innerHTML).toContain('<svg'));
    expect(screen.getByText('Билет 1 из 2')).toBeInTheDocument();
    expect(screen.getByText('Номер 4821')).toBeInTheDocument();
    const grid = screen.getByRole('list', { name: 'Данные билета' });
    for (const label of ['Гость', 'Дата', 'Вход', 'Билет']) expect(within(grid).getByText(label)).toBeInTheDocument();
    expect(within(grid).getByText('Аня')).toBeInTheDocument();
    expect(within(grid).getByText('вс, 25 окт')).toBeInTheDocument();
    expect(within(grid).getByText('23:00')).toBeInTheDocument();
    expect(within(grid).getByText('Входной')).toBeInTheDocument();
  });

  it('valid without a Telegram name still fills the guest cell', async () => {
    render(<PaperTicket ticket={ticket()} guestName={null} />);
    await waitFor(() => expect(qr()?.innerHTML).toContain('<svg'));
    expect(within(screen.getByRole('list', { name: 'Данные билета' })).getByText('—')).toBeInTheDocument();
  });

  it('used: the stub is gone, «Было · 25 окт» on the poster, no QR', () => {
    render(<PaperTicket ticket={ticket({ status: 'used', qrToken: null })} guestName="Аня" />);
    expect(qr()).toBeNull();
    expect(screen.getByText('Было · 25 окт')).toBeInTheDocument();
    expect(screen.queryByText('Номер 4821')).toBeNull();
  });

  it('used, first show: the stub is still there to tear off, without a QR', () => {
    render(<PaperTicket ticket={ticket({ status: 'used', qrToken: null })} guestName="Аня" torn={false} />);
    expect(qr()).toBeNull();
    expect(screen.getByTestId('stub')).toHaveAttribute('data-tearing');
  });

  it.each([
    ['returned', 'Возвращён'],
    ['transferred', 'Передан'],
    ['event_cancelled', 'Вечер отменён'],
  ] as const)('%s: greyed out, a stub without QR and the status in a word', (status, word) => {
    const view = render(<PaperTicket ticket={ticket({ status, qrToken: null })} guestName="Аня" />);
    expect(screen.getByText(word)).toBeInTheDocument();
    expect(qr()).toBeNull();
    expect(screen.getByTestId('stub')).toBeInTheDocument();
    expect(view.container.firstElementChild).toHaveAttribute('data-inactive');
  });
});

describe('TicketFan', () => {
  beforeAll(() => {
    // jsdom has no PointerEvent; without it fireEvent drops clientX.
    if (!('PointerEvent' in window)) {
      class PointerEventPolyfill extends MouseEvent {
        pointerId: number;
        constructor(type: string, init: PointerEventInit = {}) {
          super(type, init);
          this.pointerId = init.pointerId ?? 0;
        }
      }
      Object.defineProperty(window, 'PointerEvent', { value: PointerEventPolyfill, configurable: true });
    }
  });

  const three = [ticket({ id: 'a', position: 1, ofCount: 3 }), ticket({ id: 'b', position: 2, ofCount: 3 }), ticket({ id: 'c', position: 3, ofCount: 3 })];
  const card = (t: Ticket) => <span>{t.id}</span>;
  const current = () => screen.getByRole('region', { name: 'Билеты' }).querySelector('[data-current]')!;

  it('clamps the index to the tickets it has', () => {
    render(<TicketFan tickets={three} index={5} onIndex={vi.fn()} render={card} />);
    expect(current()).toHaveTextContent('c');
    expect(screen.getAllByRole('tab')).toHaveLength(3);
  });

  it('pages with the arrow keys and stops at the ends', async () => {
    const onIndex = vi.fn();
    const view = render(<TicketFan tickets={three} index={0} onIndex={onIndex} render={card} />);
    const fan = screen.getByRole('region', { name: 'Билеты' });
    fan.focus();
    await userEvent.keyboard('{ArrowLeft}');
    expect(onIndex).not.toHaveBeenCalled();
    await userEvent.keyboard('{ArrowRight}');
    expect(onIndex).toHaveBeenLastCalledWith(1);
    view.rerender(<TicketFan tickets={three} index={2} onIndex={onIndex} render={card} />);
    onIndex.mockClear();
    await userEvent.keyboard('{ArrowRight}');
    expect(onIndex).not.toHaveBeenCalled();
  });

  it('a swipe of more than 40 px moves to the neighbour', () => {
    const onIndex = vi.fn();
    render(<TicketFan tickets={three} index={1} onIndex={onIndex} render={card} />);
    const fan = screen.getByRole('region', { name: 'Билеты' });
    fireEvent.pointerDown(fan, { clientX: 200, pointerId: 1 });
    fireEvent.pointerMove(fan, { clientX: 170, pointerId: 1 });
    fireEvent.pointerUp(fan, { clientX: 170, pointerId: 1 });
    expect(onIndex).not.toHaveBeenCalled();
    fireEvent.pointerDown(fan, { clientX: 200, pointerId: 1 });
    fireEvent.pointerMove(fan, { clientX: 140, pointerId: 1 });
    fireEvent.pointerUp(fan, { clientX: 140, pointerId: 1 });
    expect(onIndex).toHaveBeenLastCalledWith(2);
  });

  it('a tap on the current ticket opens it, a tap on a neighbour brings it forward', async () => {
    const onIndex = vi.fn();
    const onOpen = vi.fn();
    render(<TicketFan tickets={three} index={1} onIndex={onIndex} onOpen={onOpen} render={card} />);
    await userEvent.click(screen.getByText('b'));
    expect(onOpen).toHaveBeenCalledWith(three[1]);
    await userEvent.click(screen.getByText('c'));
    expect(onIndex).toHaveBeenLastCalledWith(2);
  });
});
