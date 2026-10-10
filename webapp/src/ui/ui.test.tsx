import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { posterColor } from '../lib/posterColor';
import { createTg, mainButtonStore } from '../telegram/tg';
import { TgProvider } from '../telegram/hooks';
import { Button } from './Button';
import { Dialog } from './Dialog';
import { InPageMainButton } from './InPageMainButton';
import { Poster } from './Poster';
import { Stepper } from './Stepper';
import { TabBar } from './TabBar';

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
    render(<Poster poster={null} title="Настолки до утра" ratio="4:5" icon="dice" />);
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

describe('InPageMainButton', () => {
  it('draws the main button inside the page outside Telegram', async () => {
    const tg = createTg();
    const onClick = vi.fn();
    render(
      <TgProvider value={tg}>
        <InPageMainButton />
      </TgProvider>,
    );
    act(() => tg.mainButton.set({ text: 'Выберите билеты', enabled: false, progress: false, onClick }));
    expect(screen.getByRole('button', { name: 'Выберите билеты' })).toBeDisabled();
    act(() => tg.mainButton.set({ text: 'Оплатить 1 550 ₽', enabled: true, progress: false, onClick }));
    await userEvent.click(screen.getByRole('button', { name: 'Оплатить 1 550 ₽' }));
    expect(onClick).toHaveBeenCalledTimes(1);
    act(() => tg.mainButton.set(null));
    expect(mainButtonStore.get()).toBeNull();
    expect(screen.queryByRole('button')).toBeNull();
  });
});

describe('TabBar', () => {
  it('links the three tabs and marks the current one', () => {
    render(
      <MemoryRouter initialEntries={['/tickets']}>
        <TabBar hidden={false} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('link', { name: 'Афиша' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: 'Билеты' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Голосуем' })).toHaveAttribute('href', '/polls');
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
