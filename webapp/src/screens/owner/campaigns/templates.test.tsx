import { useQuery } from '@tanstack/react-query';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes, useLocation, useSearchParams } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { useRequiredCampaignApi } from '../../../api/campaigns/CampaignApiProvider';
import { MockCampaignApi } from '../../../api/campaigns/MockCampaignApi';
import { renderScreen, T0 } from '../../../test/render';
import { CampaignStart } from './CampaignStart';
import { TemplateEditor } from './TemplateEditor';
import { Templates } from './Templates';

/** Stands in for the campaign editor: shows the address it was opened at and the body of its template. */
function NewStub() {
  const api = useRequiredCampaignApi();
  const location = useLocation();
  const [params] = useSearchParams();
  const id = params.get('template');
  const found = useQuery({
    queryKey: ['stub', id],
    queryFn: async () => (await api.templates()).find((t) => t.id === id),
  });
  return <p data-testid="stub">{found.data ? `${location.pathname}${location.search}|${found.data.body}` : ''}</p>;
}

function App() {
  return (
    <Routes>
      <Route path="/owner/campaigns/start" element={<CampaignStart />} />
      <Route path="/owner/campaigns/templates" element={<Templates />} />
      <Route path="/owner/campaigns/templates/:id" element={<TemplateEditor />} />
      <Route path="/owner/campaigns/new" element={<NewStub />} />
    </Routes>
  );
}

function render(at: string, campaignApi = new MockCampaignApi({ latencyMs: 0, now: () => T0 })) {
  renderScreen(<App />, { at, path: '*', campaignApi });
  return { campaignApi };
}

describe('CampaignStart', () => {
  it('opens a template in the editor', async () => {
    render('/owner/campaigns/start');
    await userEvent.click(await screen.findByRole('link', { name: /Завтра вечер/ }));
    expect(await screen.findByTestId('stub')).toHaveTextContent(
      '/owner/campaigns/new?template=tb-tomorrow|Завтра «{event}». Если билета ещё нет, он тут.',
    );
  });

  it('starts from a blank page', async () => {
    render('/owner/campaigns/start');
    await userEvent.click(await screen.findByRole('link', { name: 'С чистого листа' }));
    expect(screen.getByTestId('where')).toHaveTextContent('/owner/campaigns/new');
  });

  it('says when there are no own templates', async () => {
    const api = new MockCampaignApi({ latencyMs: 0, now: () => T0 });
    await api.deleteTemplate('t-own');
    render('/owner/campaigns/start', api);
    expect(
      await screen.findByText('Своих шаблонов пока нет. Сохрани рассылку как шаблон или создай в «Шаблонах»'),
    ).toBeInTheDocument();
  });
});

describe('Templates', () => {
  it('copies a ready template into own ones', async () => {
    render('/owner/campaigns/templates');
    const card = (await screen.findByText('Осталось мало мест')).closest('li') as HTMLElement;
    expect(within(card).queryByRole('button', { name: 'Править' })).not.toBeInTheDocument();
    expect(within(card).queryByRole('button', { name: 'Удалить' })).not.toBeInTheDocument();
    await userEvent.click(within(card).getByRole('button', { name: 'Скопировать в свои' }));
    expect(await screen.findByText('Осталось мало мест (копия)')).toBeInTheDocument();
  });

  it('deletes an own template after confirmation', async () => {
    const { campaignApi } = render('/owner/campaigns/templates');
    const card = (await screen.findByText('Мой анонс')).closest('li') as HTMLElement;
    await userEvent.click(within(card).getByRole('button', { name: 'Удалить' }));
    expect(await campaignApi.templates()).toHaveLength(6);
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Удалить' }));
    expect(await screen.findByText('Своих шаблонов пока нет')).toBeInTheDocument();
    expect(await campaignApi.templates()).toHaveLength(5);
  });

  it('opens the new-template form from the bottom bar', async () => {
    render('/owner/campaigns/templates');
    await userEvent.click(await screen.findByRole('button', { name: '+ Новый шаблон' }));
    expect(screen.getByTestId('where')).toHaveTextContent('/owner/campaigns/templates/new');
  });
});

describe('TemplateEditor', () => {
  it('saves the edited name and text', async () => {
    const { campaignApi } = render('/owner/campaigns/templates/t-own');
    const name = await screen.findByLabelText('Название');
    await userEvent.clear(name);
    await userEvent.type(name, 'Скидка');
    const text = screen.getByLabelText('Текст');
    await userEvent.clear(text);
    await userEvent.type(text, '**скидка**');
    await userEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
    expect(await screen.findByRole('heading', { name: 'Шаблоны' })).toBeInTheDocument();
    const saved = (await campaignApi.templates()).find((t) => t.id === 't-own');
    expect(saved).toMatchObject({ name: 'Скидка', body: '<b>скидка</b>' });
  });

  it('creates a template', async () => {
    const { campaignApi } = render('/owner/campaigns/templates/new');
    await userEvent.click(await screen.findByRole('button', { name: 'Сохранить' }));
    expect(await screen.findByText('Назови шаблон')).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('Название'), 'Новый');
    await userEvent.type(screen.getByLabelText('Текст'), 'Привет');
    await userEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
    await screen.findByRole('heading', { name: 'Шаблоны' });
    expect((await campaignApi.templates()).some((t) => t.name === 'Новый' && t.body === 'Привет')).toBe(true);
  });

  it('shows a ready template read-only with a way to copy it', async () => {
    const { campaignApi } = render('/owner/campaigns/templates/tb-few');
    expect(await screen.findByLabelText('Название')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Сохранить' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Скопировать в свои' }));
    await screen.findByRole('heading', { name: 'Шаблоны' });
    expect((await campaignApi.templates()).some((t) => t.name === 'Осталось мало мест (копия)')).toBe(true);
  });
});
