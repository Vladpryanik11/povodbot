import type { Direction, EventDetail, Poster, Ticket } from '../types';

const MSK_OFFSET_MS = 3 * 60 * 60 * 1000;
export const MOSCOW = 'Europe/Moscow';

/** ISO time of hh:mm Moscow time, `days` after the Moscow date of `now`. Moscow has no DST. */
export function mskAt(now: number, days: number, hh: number, mm = 0): string {
  const local = new Date(now + MSK_OFFSET_MS);
  const utc = Date.UTC(local.getUTCFullYear(), local.getUTCMonth(), local.getUTCDate() + days, hh, mm);
  return new Date(utc - MSK_OFFSET_MS).toISOString();
}

export interface MockPollOption {
  id: string;
  title: string;
  count: number;
}

export interface MockPoll {
  id: string;
  eventId: string | null;
  question: string;
  closesAt: string;
  closed: boolean;
  options: MockPollOption[];
  myOptionId: string | null;
}

/** Event as the mock server stores it; `serverSeatsLeft` lets a scenario disagree with the showcase. */
export type MockEvent = Omit<EventDetail, 'poll' | 'minPriceKopecks' | 'soldOut'> & {
  serverSeatsLeft?: number;
};

export interface Fixtures {
  directions: Direction[];
  events: MockEvent[];
  tickets: Ticket[];
  polls: MockPoll[];
}

const poster = (url: string, width: number, height: number, focusX = 0.5, focusY = 0.4): Poster => ({
  url,
  width,
  height,
  focusX,
  focusY,
});

export function buildFixtures(now: number): Fixtures {
  const directions: Direction[] = [
    { id: 'd-film', title: 'Кино', icon: 'film' },
    { id: 'd-games', title: 'Настолки', icon: 'dice' },
    { id: 'd-talk', title: 'Разговоры', icon: 'talk' },
    { id: 'd-party', title: 'Вечеринки', icon: 'party' },
  ];

  const film: MockEvent = {
    id: 'e-film',
    title: 'Повод для киновечера',
    description:
      'Смотрим кино на большом экране, с пледами и чаем. Что смотрим — решаем вместе: голосуйте ниже, победитель идёт на экран :)',
    startsAt: mskAt(now, 6, 20),
    timezone: MOSCOW,
    address: 'Москва, Малая Дмитровка, 6',
    mapUrl: 'https://yandex.ru/maps/?text=Москва, Малая Дмитровка, 6',
    poster: poster('./mock/kino.jpg', 800, 1000, 0.3, 0.4),
    directionId: 'd-film',
    seatsLeft: 5,
    ticketTypes: [{ id: 'tt-film', name: 'Входной', priceKopecks: 155000, seatsLeft: 5 }],
  };

  const games: MockEvent = {
    id: 'e-games',
    title: 'Настолки до утра',
    description: 'Кодовые имена, Имаджинариум и всё, что принесёте. Новичкам объясним правила.',
    startsAt: mskAt(now, 8, 19),
    timezone: MOSCOW,
    address: 'Москва, Покровка, 12',
    mapUrl: null,
    poster: null,
    directionId: 'd-games',
    seatsLeft: 16,
    ticketTypes: [
      { id: 'tt-games', name: 'Входной', priceKopecks: 90000, seatsLeft: 12 },
      { id: 'tt-games-pair', name: 'С другом', priceKopecks: 160000, seatsLeft: 4 },
    ],
  };

  const talk: MockEvent = {
    id: 'e-talk',
    title: 'Разговоры о важном: что держит нас в большом городе',
    description: 'Камерный вечер в кругу на 20 человек. Модератор следит, чтобы всем хватило слова.',
    startsAt: mskAt(now, 14, 19, 30),
    timezone: MOSCOW,
    address: null,
    mapUrl: null,
    poster: poster('./mock/talk.jpg', 1600, 800),
    directionId: 'd-talk',
    seatsLeft: 20,
    ticketTypes: [{ id: 'tt-talk', name: 'Входной', priceKopecks: 70000, seatsLeft: 20 }],
  };

  const party: MockEvent = {
    id: 'e-party',
    title: 'Квартирник «Тёплый ламповый»',
    description: 'Акустика, свечи и много своих. Все места разобрали за два дня.',
    startsAt: mskAt(now, 20, 21),
    timezone: MOSCOW,
    address: 'Москва, Чистопрудный бульвар, 14',
    mapUrl: null,
    poster: poster('./mock/party.jpg', 800, 1000),
    directionId: 'd-party',
    seatsLeft: 0,
    ticketTypes: [{ id: 'tt-party', name: 'Входной', priceKopecks: 120000, seatsLeft: 0 }],
  };

  const ticket = (over: Partial<Ticket> & Pick<Ticket, 'id' | 'status'>): Ticket => ({
    eventId: film.id,
    eventTitle: film.title,
    startsAt: film.startsAt,
    timezone: MOSCOW,
    address: film.address,
    mapUrl: film.mapUrl,
    typeName: 'Входной',
    position: 1,
    ofCount: 1,
    shortCode: '4821',
    qrToken: null,
    poster: film.poster,
    ...over,
  });

  const tickets: Ticket[] = [
    ticket({ id: 'tk-1', status: 'valid', position: 1, ofCount: 2, shortCode: '4821', qrToken: 'pv1.tk-1.Zm9yLWRlbW8tb25seQ' }),
    ticket({ id: 'tk-2', status: 'valid', position: 2, ofCount: 2, shortCode: '4822', qrToken: 'pv1.tk-2.ZGVtby1zZWNvbmQtdGlja2V0' }),
    ticket({
      id: 'tk-3',
      status: 'transferred',
      eventId: games.id,
      eventTitle: games.title,
      startsAt: games.startsAt,
      address: games.address,
      poster: null,
      shortCode: '7310',
    }),
    ticket({
      id: 'tk-4',
      status: 'used',
      eventId: 'e-past-film',
      eventTitle: 'Кино в сентябре',
      startsAt: mskAt(now, -20, 20),
      poster: null,
      shortCode: '1102',
    }),
    ticket({
      id: 'tk-5',
      status: 'returned',
      eventId: 'e-past-games',
      eventTitle: 'Настолки в сентябре',
      startsAt: mskAt(now, -10, 19),
      poster: null,
      shortCode: '1544',
    }),
  ];

  const polls: MockPoll[] = [
    {
      id: 'p-film',
      eventId: film.id,
      question: 'Что смотрим в пятницу?',
      closesAt: mskAt(now, 6, 18),
      closed: false,
      myOptionId: null,
      options: [
        { id: 'po-amelie', title: 'Амели', count: 14 },
        { id: 'po-lalaland', title: 'Ла-Ла Ленд', count: 10 },
        { id: 'po-budapest', title: 'Отель «Гранд Будапешт»', count: 0 },
      ],
    },
    {
      id: 'p-games',
      eventId: null,
      question: 'Во что играем в субботу?',
      closesAt: mskAt(now, -3, 18),
      closed: true,
      myOptionId: 'po-imaginarium',
      options: [
        { id: 'po-codenames', title: 'Кодовые имена', count: 9 },
        { id: 'po-imaginarium', title: 'Имаджинариум', count: 12 },
        { id: 'po-mafia', title: 'Мафия', count: 5 },
      ],
    },
  ];

  return { directions, events: [film, games, talk, party], tickets, polls };
}
