import { MOSCOW, mskAt } from '../mock/fixtures';
import type { Poster } from '../types';
import type { EventStatus, OwnerDirection, OwnerEvent } from './types';

export interface OwnerFixtures {
  directions: OwnerDirection[];
  events: OwnerEvent[];
}

/** A poster stored before the owner screens existed: a bare URL, size unknown (0×0). */
export const LEGACY_POSTER_URL = './mock/tiny.jpg';

interface Seed {
  id: string;
  title: string;
  description: string;
  directionId: string;
  days: number;
  status: EventStatus;
  poster: Poster | null;
  sold: number;
  accentColor?: string;
}

function poster(url: string, width: number, height: number): Poster {
  return { url, focusX: 0.5, focusY: 0.4, width, height };
}

/** Every event has the whole form filled and one active ticket, so publishing trips only on what a test removes. */
export function buildOwnerFixtures(now: number): OwnerFixtures {
  const directions: OwnerDirection[] = [
    { id: 'd-film', name: 'Киновечер' },
    { id: 'd-workshop', name: 'Мастерклассы' },
    { id: 'd-book', name: 'Книжный клуб' },
  ];
  const seeds: Seed[] = [
    {
      id: 'e-own-film',
      title: 'Кино на крыше: «Амели»',
      description: 'Смотрим, потом спорим за чаем.',
      directionId: 'd-film',
      days: 3,
      status: 'published',
      poster: poster('./mock/kino.jpg', 800, 1000),
      sold: 18,
      accentColor: '#E8A33D',
    },
    {
      id: 'e-own-free',
      title: 'Разговор о городе',
      description: 'Открытая встреча с архитектором.',
      directionId: 'd-book',
      days: 5,
      status: 'published',
      poster: poster('./mock/talk.jpg', 1600, 800),
      sold: 0,
    },
    {
      id: 'e-own-workshop',
      title: 'Мастерская: керамика',
      description: 'Лепим чашки, обжиг — через неделю.',
      directionId: 'd-workshop',
      days: 7,
      status: 'draft',
      poster: poster('./mock/party.jpg', 800, 1000),
      sold: 0,
    },
    {
      id: 'e-own-book',
      title: 'Книжный клуб: Пелевин',
      description: 'Читаем «Generation П» и обсуждаем.',
      directionId: 'd-book',
      days: 10,
      status: 'draft',
      poster: null,
      sold: 0,
    },
    {
      id: 'e-own-past',
      title: 'Кино: «Сталкер»',
      description: 'Длинный вечер Тарковского.',
      directionId: 'd-film',
      days: -5,
      status: 'completed',
      poster: poster('./mock/kino.jpg', 800, 1000),
      sold: 25,
    },
    {
      id: 'e-own-legacy',
      title: 'Старый постер',
      description: 'Постер загружен ссылкой ещё до режима владельца.',
      directionId: 'd-workshop',
      days: 12,
      status: 'draft',
      poster: { url: LEGACY_POSTER_URL, focusX: 0.5, focusY: 0.5, width: 0, height: 0 },
      sold: 0,
    },
  ];
  const created = mskAt(now, -14, 12);
  const events = seeds.map(
    (s): OwnerEvent => ({
      id: s.id,
      title: s.title,
      description: s.description,
      directionId: s.directionId,
      startsAt: mskAt(now, s.days, 19),
      endsAt: mskAt(now, s.days, 23),
      timezone: MOSCOW,
      address: 'Покровка, 1',
      mapUrl: 'https://yandex.ru/maps/-/povod',
      capacity: 30,
      ticketTypes: [
        { id: `${s.id}-t1`, name: 'Входной', priceKopecks: 150000, currency: 'RUB', limit: 30, active: true },
      ],
      status: s.status,
      publishedAt: s.status === 'draft' ? null : mskAt(now, -7, 12),
      createdAt: created,
      updatedAt: created,
      accentColor: s.accentColor ?? null,
      poster: s.poster,
      sold: s.sold,
    }),
  );
  return { directions, events };
}
