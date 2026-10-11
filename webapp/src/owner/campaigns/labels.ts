import type { AudienceRelation, Campaign, PurchaseFilter } from '../../api/campaigns/types';
import { formatDateTime, plural } from '../../lib/format';
import type { PillTone } from '../../ui/Pill';
import { CLUB_TIMEZONE } from '../form';

export function campaignStatus(
  c: Pick<Campaign, 'status' | 'scheduledAt' | 'cancelReason'>,
): { text: string; tone: PillTone } {
  switch (c.status) {
    case 'draft':
      return { text: 'Черновик', tone: 'muted' };
    case 'scheduled':
      return {
        text: c.scheduledAt ? `Запланирована · ${formatDateTime(c.scheduledAt, CLUB_TIMEZONE)}` : 'Запланирована',
        tone: 'accent',
      };
    case 'running':
      return { text: 'Идёт отправка', tone: 'warning' };
    case 'completed':
      return { text: 'Отправлена', tone: 'success' };
    case 'stopped':
      return { text: 'Остановлена', tone: 'muted' };
    case 'cancelled':
      return {
        text: c.cancelReason === 'event_unpublished' ? 'Отменена · вечер снят с публикации' : 'Отменена',
        tone: 'muted',
      };
  }
}

/** The worker's own codes first; anything else is Telegram's text, matched by what it says. */
const TELEGRAM_REASONS: [RegExp, string][] = [
  [/chat not found/i, 'Чат с гостем не найден'],
  [/user is deactivated/i, 'Аккаунт гостя удалён'],
  [/wrong file|photo|image|http url content|wrong type of the web page/i, 'Telegram не принял картинку'],
  [/can't parse entities/i, 'Telegram не разобрал оформление текста'],
  [/too many requests|retry after/i, 'Telegram попросил подождать'],
  [/timeout|timed out|connect/i, 'Не было связи с Telegram'],
];

const OWN_REASONS: Record<string, string> = {
  bot_blocked: 'Заблокировали бота',
  recipient_not_eligible: 'Отказались от рассылок или заблокировали бота',
  unknown: 'Причина неизвестна',
};

export function failureLabel(reason: string): string {
  return OWN_REASONS[reason] ?? TELEGRAM_REASONS.find(([pattern]) => pattern.test(reason))?.[1] ?? 'Ошибка Telegram';
}

export function groupFailures(reasons: Record<string, number>): { label: string; count: number }[] {
  const sums = new Map<string, number>();
  for (const [reason, count] of Object.entries(reasons)) {
    const label = failureLabel(reason);
    sums.set(label, (sums.get(label) ?? 0) + count);
  }
  return [...sums].map(([label, count]) => ({ label, count })).sort((a, b) => b.count - a.count);
}

export const RELATION_LABEL: Record<AudienceRelation, string> = {
  going: 'Идут на вечер',
  liked: 'Лайкнули',
  liked_not_bought: 'Лайкнули, но не купили',
  attended: 'Были на вечере',
};

export const PURCHASE_LABEL: Record<PurchaseFilter, string> = {
  any: 'Неважно',
  bought: 'Покупали',
  never: 'Ни разу не покупали',
};

export function guestsLabel(n: number): string {
  return `${n} ${plural(n, ['гость', 'гостя', 'гостей'])}`;
}
