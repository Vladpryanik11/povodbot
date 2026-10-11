import { mskAt } from '../mock/fixtures';
import { buildOwnerFixtures } from '../owner/ownerFixtures';
import type { EventStatus } from '../owner/types';
import {
  EMPTY_AUDIENCE,
  type Campaign,
  type CampaignButton,
  type CampaignStats,
  type CampaignTemplate,
} from './types';

/** What the campaign side knows of an event: enough to check, count and show its cover. */
export interface CampaignEventRef {
  id: string;
  title: string;
  startsAt: string;
  status: EventStatus;
  directionId: string;
  sold: number;
  posterUrl: string | null;
}

export interface CampaignFixtures {
  campaigns: Campaign[];
  stats: Record<string, CampaignStats>;
  templates: CampaignTemplate[];
  events: CampaignEventRef[];
}

const OPEN_EVENT: CampaignButton[] = [{ kind: 'event', label: 'Открыть вечер' }];

/** The ready templates of migrations/versions/0010_broadcasts.py, word for word. */
const BUILTIN: [string, string, string, CampaignTemplate['imageKind'], CampaignButton[]][] = [
  ['tb-new', 'Новый вечер в афише', '{date} у нас «{event}». Билеты уже можно взять.', 'event', OPEN_EVENT],
  [
    'tb-few',
    'Осталось мало мест',
    'На «{event}» осталось совсем немного мест. Если думаешь пойти, лучше не откладывать.',
    'event',
    OPEN_EVENT,
  ],
  ['tb-tomorrow', 'Завтра вечер', 'Завтра «{event}». Если билета ещё нет, он тут.', 'event', OPEN_EVENT],
  ['tb-thanks', 'Спасибо, что пришли', 'Спасибо за «{event}», было здорово. Следующий вечер уже в афише.', 'none', []],
  ['tb-moved', 'Вечер перенесён', 'С «{event}» поменялись планы. Все подробности по кнопке.', 'event', OPEN_EVENT],
];

const zeroStats = (bought: number | null): CampaignStats => ({
  recipients: 0,
  delivered: 0,
  failed: 0,
  failedReasons: {},
  skippedLimit: 0,
  clicked: 0,
  anonymousClicks: 0,
  bought,
});

export { zeroStats };

function campaign(fields: Partial<Campaign> & Pick<Campaign, 'id' | 'title' | 'body' | 'status'>): Campaign {
  return {
    image: { kind: 'none' },
    buttons: [],
    eventId: null,
    audience: EMPTY_AUDIENCE,
    scheduledAt: null,
    startedAt: null,
    finishedAt: null,
    recipientCount: null,
    cancelReason: null,
    updatedAt: '',
    ...fields,
  };
}

/** Every status once; ids are stable because tests lean on them. Versions are stamped by the mock. */
export function buildCampaignFixtures(now: number): CampaignFixtures {
  const events = buildOwnerFixtures(now).events.map((e) => ({
    id: e.id,
    title: e.title,
    startsAt: e.startsAt,
    status: e.status,
    directionId: e.directionId,
    sold: e.sold,
    posterUrl: e.poster?.url ?? null,
  }));
  const minutesAgo = (m: number) => new Date(now - m * 60_000).toISOString();
  const campaigns: Campaign[] = [
    campaign({
      id: 'c-gone',
      title: 'Мастерская',
      body: 'Собираем мастерскую. Приходи с идеями.',
      status: 'draft',
      eventId: 'e-own-workshop',
    }),
    campaign({
      id: 'c-draft',
      title: 'Анонс «Амели»',
      body: 'Во вторник <b>«Амели»</b> на крыше. Пледы и чай за нами.',
      status: 'draft',
      eventId: 'e-own-film',
      image: { kind: 'event' },
      buttons: OPEN_EVENT,
      audience: { ...EMPTY_AUDIENCE, event: { id: 'e-own-film', relation: 'liked' } },
    }),
    campaign({
      id: 'c-scheduled',
      title: 'Осталось мало мест на «Амели»',
      body: 'На «Кино на крыше: «Амели»» осталось совсем немного мест. Если думаешь пойти, лучше не откладывать.',
      status: 'scheduled',
      eventId: 'e-own-film',
      image: { kind: 'event' },
      buttons: OPEN_EVENT,
      scheduledAt: mskAt(now, 2, 12),
    }),
    campaign({
      id: 'c-stopped',
      title: 'Книжный клуб: набор',
      body: 'Собираем книжный клуб. Первая встреча — в конце месяца.',
      status: 'stopped',
      startedAt: mskAt(now, -2, 12),
      finishedAt: mskAt(now, -2, 12, 4),
      recipientCount: 120,
    }),
    campaign({
      id: 'c-done',
      title: 'Спасибо за «Сталкера»',
      body: 'Спасибо за «Кино: «Сталкер»», было здорово. Следующий вечер уже в афише.',
      status: 'completed',
      eventId: 'e-own-past',
      startedAt: mskAt(now, -4, 12),
      finishedAt: mskAt(now, -4, 12, 20),
      recipientCount: 214,
    }),
    campaign({
      id: 'c-running',
      title: 'Разговор о городе',
      body: 'В субботу говорим о городе. Вход свободный, <i>чай за нами</i>.',
      status: 'running',
      eventId: 'e-own-free',
      image: { kind: 'event' },
      buttons: OPEN_EVENT,
      startedAt: minutesAgo(10),
      recipientCount: 214,
    }),
    campaign({
      id: 'c-cancelled',
      title: 'Мастерская по керамике',
      body: 'Лепим чашки. Глина и печь — наши.',
      status: 'cancelled',
      eventId: 'e-own-workshop',
      scheduledAt: mskAt(now, 1, 12),
      cancelReason: 'event_unpublished',
    }),
  ];
  const stats: Record<string, CampaignStats> = {
    'c-done': {
      recipients: 214,
      delivered: 205,
      failed: 6,
      failedReasons: {
        bot_blocked: 3,
        recipient_not_eligible: 1,
        'Telegram server says - Bad Request: chat not found': 2,
      },
      skippedLimit: 3,
      clicked: 37,
      anonymousClicks: 4,
      bought: 5,
    },
    'c-running': { ...zeroStats(1), recipients: 214, delivered: 120, failed: 2, failedReasons: { bot_blocked: 2 }, clicked: 8 },
    'c-stopped': { ...zeroStats(null), recipients: 120, delivered: 64, clicked: 5, anonymousClicks: 1 },
  };
  const templates: CampaignTemplate[] = [
    ...BUILTIN.map(([id, name, body, imageKind, buttons]) => ({
      id,
      name,
      body,
      imageKind,
      buttons,
      isBuiltin: true,
      updatedAt: '2026-10-01T00:00:00+00:00',
    })),
    {
      id: 't-own',
      name: 'Мой анонс',
      body: '<b>{event}</b> — {date}. Приходи, будет тепло.',
      imageKind: 'event',
      buttons: OPEN_EVENT,
      isBuiltin: false,
      updatedAt: '2026-10-05T00:00:00+00:00',
    },
  ];
  return { campaigns, stats, templates, events };
}
