import { describe, expect, it } from 'vitest';
import { campaignStatus, failureLabel, groupFailures, guestsLabel } from './labels';

describe('failureLabel', () => {
  it.each([
    ['bot_blocked', 'Заблокировали бота'],
    ['recipient_not_eligible', 'Отказались от рассылок или заблокировали бота'],
    ['unknown', 'Причина неизвестна'],
    ['Telegram server says - Bad Request: chat not found', 'Чат с гостем не найден'],
    ['Forbidden: user is deactivated', 'Аккаунт гостя удалён'],
    ['Bad Request: wrong file identifier/HTTP URL specified', 'Telegram не принял картинку'],
    ['Bad Request: failed to get HTTP URL content', 'Telegram не принял картинку'],
    ['Bad Request: wrong type of the web page content', 'Telegram не принял картинку'],
    ["Bad Request: can't parse entities: unclosed tag", 'Telegram не разобрал оформление текста'],
    ['Too Many Requests: retry after 5', 'Telegram попросил подождать'],
    ['Request timeout error', 'Не было связи с Telegram'],
    ['Cannot connect to host api.telegram.org', 'Не было связи с Telegram'],
    ['Bad Request: message is too long', 'Ошибка Telegram'],
  ])('%s', (reason, label) => {
    expect(failureLabel(reason)).toBe(label);
  });
});

it('groups failures by their label, most first', () => {
  expect(
    groupFailures({
      bot_blocked: 3,
      'Bad Request: chat not found': 2,
      'Telegram server says - Bad Request: chat not found': 2,
      recipient_not_eligible: 1,
    }),
  ).toEqual([
    { label: 'Чат с гостем не найден', count: 4 },
    { label: 'Заблокировали бота', count: 3 },
    { label: 'Отказались от рассылок или заблокировали бота', count: 1 },
  ]);
});

describe('campaignStatus', () => {
  it('says why it was cancelled', () => {
    expect(
      campaignStatus({ status: 'cancelled', scheduledAt: null, cancelReason: 'event_unpublished' }),
    ).toEqual({ text: 'Отменена · вечер снят с публикации', tone: 'muted' });
    expect(campaignStatus({ status: 'cancelled', scheduledAt: null, cancelReason: null }).text).toBe('Отменена');
  });

  it('shows when a scheduled one goes out, Moscow time', () => {
    const status = campaignStatus({
      status: 'scheduled',
      scheduledAt: '2026-10-12T09:00:00Z',
      cancelReason: null,
    });
    expect(status.tone).toBe('accent');
    expect(status.text).toMatch(/^Запланирована · .*12:00$/);
  });
});

it('counts guests in Russian', () => {
  expect([guestsLabel(1), guestsLabel(3), guestsLabel(214)]).toEqual(['1 гость', '3 гостя', '214 гостей']);
});
