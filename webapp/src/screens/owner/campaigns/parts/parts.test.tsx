import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState, type ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CampaignApiProvider } from '../../../../api/campaigns/CampaignApiProvider';
import { CMSG } from '../../../../api/campaigns/messages';
import { MockCampaignApi } from '../../../../api/campaigns/MockCampaignApi';
import { EMPTY_AUDIENCE, type AudienceFilter, type CampaignButton } from '../../../../api/campaigns/types';
import { useAudienceCount } from '../../../../owner/campaigns/useAudienceCount';
import { T0 } from '../../../../test/render';
import { ButtonsEditor } from './ButtonsEditor';
import { MessageBubble } from './MessageBubble';
import { TextEditor } from './TextEditor';

function Text({ initial, limit = 4096 }: { initial: string; limit?: number }) {
  const [value, setValue] = useState(initial);
  return (
    <>
      <TextEditor id="body" value={value} onChange={setValue} limit={limit} />
      <output data-testid="value">{value}</output>
    </>
  );
}

const area = () => screen.getByLabelText('Текст') as HTMLTextAreaElement;

describe('TextEditor', () => {
  it('wraps the selection in bold', async () => {
    render(<Text initial="Кино на крыше" />);
    area().setSelectionRange(0, 4);
    await userEvent.click(screen.getByRole('button', { name: 'Жирный' }));
    expect(screen.getByTestId('value')).toHaveTextContent('**Кино** на крыше');
  });

  it('inserts only https links', async () => {
    render(<Text initial="Кино" />);
    area().setSelectionRange(0, 4);
    await userEvent.click(screen.getByRole('button', { name: 'Ссылка' }));
    const url = screen.getByLabelText('Адрес ссылки');
    await userEvent.clear(url);
    await userEvent.type(url, 'http://a.ru');
    await userEvent.click(screen.getByRole('button', { name: 'Вставить' }));
    expect(screen.getByText(CMSG.httpsOnly)).toBeInTheDocument();
    await userEvent.clear(url);
    await userEvent.type(url, 'https://a.ru');
    await userEvent.click(screen.getByRole('button', { name: 'Вставить' }));
    expect(screen.getByTestId('value')).toHaveTextContent('[Кино](https://a.ru)');
  });

  it('counts like Telegram, an emoji is two', () => {
    render(<Text initial={'a'.repeat(1023) + '😀'} limit={1024} />);
    expect(screen.getByText('1025 / 1024')).toBeInTheDocument();
    expect(screen.getByText(CMSG.tooLong)).toBeInTheDocument();
  });
});

describe('ButtonsEditor', () => {
  function Buttons({ hasEvent }: { hasEvent: boolean }) {
    const [buttons, setButtons] = useState<CampaignButton[]>([]);
    return <ButtonsEditor buttons={buttons} onChange={setButtons} hasEvent={hasEvent} />;
  }

  it('stops at two buttons', async () => {
    render(<Buttons hasEvent />);
    await userEvent.click(screen.getByRole('button', { name: '+ Кнопка' }));
    await userEvent.click(screen.getByRole('button', { name: '+ Кнопка' }));
    expect(screen.queryByRole('button', { name: '+ Кнопка' })).not.toBeInTheDocument();
  });

  it('cannot open an evening without one', async () => {
    render(<Buttons hasEvent={false} />);
    await userEvent.click(screen.getByRole('button', { name: '+ Кнопка' }));
    expect(screen.getByRole('option', { name: 'Открыть вечер' })).toBeDisabled();
    expect(screen.getByLabelText('Адрес')).toBeInTheDocument();
  });
});

describe('useAudienceCount', () => {
  afterEach(() => vi.useRealTimers());

  it('asks once, 300 ms after the last change', async () => {
    vi.useFakeTimers();
    const api = new MockCampaignApi({ latencyMs: 0, now: () => T0 });
    const spy = vi.spyOn(api, 'audienceCount');
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>
        <CampaignApiProvider api={api}>{children}</CampaignApiProvider>
      </QueryClientProvider>
    );
    const { rerender } = renderHook((filter: AudienceFilter) => useAudienceCount(filter), {
      wrapper,
      initialProps: EMPTY_AUDIENCE,
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    spy.mockClear();
    for (const purchases of ['bought', 'never', 'bought'] as const) {
      rerender({ ...EMPTY_AUDIENCE, purchases });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(100);
      });
    }
    expect(spy).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith({ ...EMPTY_AUDIENCE, purchases: 'bought' });
  });
});

describe('MessageBubble', () => {
  it('shows markup, never raw HTML', () => {
    const { container } = render(<MessageBubble markup="<script>x</script> **ok**" imageUrl={null} buttons={[]} />);
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('b')).toHaveTextContent('ok');
    expect(screen.getByText(/<script>x<\/script>/)).toBeInTheDocument();
  });

  it('shows a placeholder for no text and the buttons under it', () => {
    render(<MessageBubble markup="" imageUrl={null} buttons={[{ kind: 'event', label: 'Открыть вечер' }]} />);
    expect(screen.getByText('Здесь будет текст')).toBeInTheDocument();
    expect(screen.getByText('Открыть вечер')).toBeInTheDocument();
  });
});
