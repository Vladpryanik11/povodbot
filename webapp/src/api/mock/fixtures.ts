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

const AVATARS = ['./mock/avatar-1.svg', './mock/avatar-2.svg', './mock/avatar-3.svg'];
const going = () => ({ count: 23, avatars: [...AVATARS] });
const nobody = () => ({ count: 0, avatars: [] });

export function buildFixtures(now: number): Fixtures {
  const directions: Direction[] = [
    { id: 'd-film', title: 'Киновечер', icon: 'film' },
    { id: 'd-workshop', title: 'Мастерклассы', icon: 'workshop' },
    { id: 'd-book', title: 'Книжный клуб', icon: 'book' },
  ];

  const film: MockEvent = {
    id: 'e-film',
    title: 'Амели на большом экране',
    description: 'Смотрим «Амели» на большом экране, с пледами и чаем. Приходи за полчаса — займёшь место поудобнее.',
    startsAt: mskAt(now, 0, 23),
    timezone: MOSCOW,
    address: 'Москва, Малая Дмитровка, 6',
    mapUrl: 'https://yandex.ru/maps/?text=Москва, Малая Дмитровка, 6',
    poster: poster('./mock/kino.jpg', 800, 1000, 0.3, 0.4),
    directionId: 'd-film',
    accentColor: null,
    attendees: going(),
    seatsLeft: 5,
    ticketTypes: [{ id: 'tt-film', name: 'Входной', priceKopecks: 155000, seatsLeft: 5 }],
  };

  const workshop: MockEvent = {
    id: 'e-workshop',
    title: 'Лепим чашку из глины',
    description: 'Гончар покажет, как из комка глины получается чашка. Фартуки и чай наши, руки твои.',
    startsAt: mskAt(now, 2, 19),
    timezone: MOSCOW,
    address: 'Москва, Покровка, 12',
    mapUrl: null,
    poster: poster('./mock/party.jpg', 800, 1000),
    directionId: 'd-workshop',
    accentColor: '#2B6FFF',
    attendees: going(),
    seatsLeft: 16,
    ticketTypes: [
      { id: 'tt-workshop', name: 'Входной', priceKopecks: 90000, seatsLeft: 12 },
      { id: 'tt-workshop-pair', name: 'С другом', priceKopecks: 160000, seatsLeft: 4 },
    ],
  };

  const book: MockEvent = {
    id: 'e-book',
    title: 'Книжный клуб: «Мастер и Маргарита»',
    description: 'Камерный круг на 20 человек. Дочитать не обязательно — главное, чтобы было что сказать.',
    startsAt: mskAt(now, 4, 19, 30),
    timezone: MOSCOW,
    address: null,
    mapUrl: null,
    poster: null,
    directionId: 'd-book',
    accentColor: null,
    attendees: nobody(),
    seatsLeft: 20,
    ticketTypes: [{ id: 'tt-book', name: 'Входной', priceKopecks: 70000, seatsLeft: 20 }],
  };

  const film2: MockEvent = {
    id: 'e-film-2',
    title: 'Ла-Ла Ленд и попкорн',
    description: 'Мюзикл, который хочется пересматривать. Попкорн и лимонад — за наш счёт.',
    startsAt: mskAt(now, 9, 20),
    timezone: MOSCOW,
    address: 'Москва, Малая Дмитровка, 6',
    mapUrl: 'https://yandex.ru/maps/?text=Москва, Малая Дмитровка, 6',
    poster: poster('./mock/talk.jpg', 1600, 800),
    directionId: 'd-film',
    accentColor: null,
    attendees: going(),
    seatsLeft: 30,
    ticketTypes: [{ id: 'tt-film-2', name: 'Входной', priceKopecks: 155000, seatsLeft: 30 }],
  };

  const workshop2: MockEvent = {
    id: 'e-workshop-2',
    title: 'Коктейли без спешки',
    description: 'Бармен научит трём классическим коктейлям и одному своему. Все места разобрали за два дня.',
    startsAt: mskAt(now, 12, 19),
    timezone: MOSCOW,
    address: 'Москва, Чистопрудный бульвар, 14',
    mapUrl: null,
    poster: poster('./mock/tiny.jpg', 400, 500),
    directionId: 'd-workshop',
    accentColor: null,
    attendees: nobody(),
    seatsLeft: 0,
    ticketTypes: [{ id: 'tt-workshop-2', name: 'Входной', priceKopecks: 120000, seatsLeft: 0 }],
  };

  const book2: MockEvent = {
    id: 'e-book-2',
    title: 'Книжный клуб: Пелевин и чай',
    description: 'Разбираем «Generation П» за большим столом. Чай, печенье и споры до хрипоты.',
    startsAt: mskAt(now, 20, 19),
    timezone: MOSCOW,
    address: 'Москва, Покровка, 12',
    mapUrl: null,
    poster: poster('./mock/kino.jpg', 800, 1000, 0.7, 0.6),
    directionId: 'd-book',
    accentColor: null,
    attendees: nobody(),
    seatsLeft: 14,
    ticketTypes: [{ id: 'tt-book-2', name: 'Входной', priceKopecks: 70000, seatsLeft: 14 }],
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
    ticket({ id: 'tk-1', status: 'valid', shortCode: '4821', qrToken: 'pv1.tk-1.Zm9yLWRlbW8tb25seQ' }),
    ticket({
      id: 'tk-3',
      status: 'transferred',
      eventId: workshop.id,
      eventTitle: workshop.title,
      startsAt: workshop.startsAt,
      address: workshop.address,
      mapUrl: null,
      poster: workshop.poster,
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
      eventId: 'e-past-book',
      eventTitle: 'Книжный клуб в сентябре',
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
      question: 'Что лепим в следующий раз?',
      closesAt: mskAt(now, -3, 18),
      closed: true,
      myOptionId: 'po-imaginarium',
      options: [
        { id: 'po-codenames', title: 'Тарелку', count: 9 },
        { id: 'po-imaginarium', title: 'Вазу', count: 12 },
        { id: 'po-mafia', title: 'Подсвечник', count: 5 },
      ],
    },
  ];

  return { directions, events: [film, workshop, book, film2, workshop2, book2], tickets, polls };
}
