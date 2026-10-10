const NBSP = ' ';

/** Russian plural: forms are [one, few, many] — «билет», «билета», «билетов». */
export function plural(n: number, forms: [string, string, string]): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return forms[0];
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return forms[1];
  return forms[2];
}

export function ticketsLabel(n: number): string {
  return `${n} ${plural(n, ['билет', 'билета', 'билетов'])}`;
}

export function seatsLabel(n: number): string {
  if (n <= 0) return 'мест нет';
  return `осталось ${n} ${plural(n, ['место', 'места', 'мест'])}`;
}

export function formatDate(iso: string, timeZone: string): string {
  const parts = new Intl.DateTimeFormat('ru-RU', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    timeZone,
  }).formatToParts(new Date(iso));
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    (parts.find((p) => p.type === type)?.value ?? '').replace('.', '');
  return `${get('weekday')}, ${get('day')} ${get('month')}`;
}

export function formatTime(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone,
  }).format(new Date(iso));
}

export function formatDateTime(iso: string, timeZone: string): string {
  return `${formatDate(iso, timeZone)} · ${formatTime(iso, timeZone)}`;
}

export function formatPrice(kopecks: number): string {
  const rubles = Math.round(kopecks / 100);
  const grouped = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 })
    .format(rubles)
    .replace(/[\s ]/g, NBSP);
  return `${grouped}${NBSP}₽`;
}

/** 'YYYY-MM-DD' of the instant in the event timezone; keys compare as strings. */
export function dayKey(iso: string, timeZone: string): string {
  const parts = new Intl.DateTimeFormat('en-CA', { year: 'numeric', month: '2-digit', day: '2-digit', timeZone }).formatToParts(
    new Date(iso),
  );
  const get = (type: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === type)?.value ?? '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}

/** Weekday and day number of a day key, for the date strip: { dow: 'пн', day: 12 }. */
export function shortDay(key: string): { dow: string; day: number } {
  const date = new Date(`${key}T12:00:00Z`);
  const dow = new Intl.DateTimeFormat('ru-RU', { weekday: 'short', timeZone: 'UTC' }).format(date).replace('.', '');
  return { dow, day: date.getUTCDate() };
}

const DAY_MS = 24 * 60 * 60 * 1000;
/** «в этот понедельник», «в эту среду», «в это воскресенье» — by the UTC weekday of a day key. */
const THIS_WEEKDAY = [
  'в это воскресенье',
  'в этот понедельник',
  'в этот вторник',
  'в эту среду',
  'в этот четверг',
  'в эту пятницу',
  'в эту субботу',
];

/** Billboard line under the title: «Сегодня в 20:00», «Завтра в 20:00», «Уже в эту субботу», «чт, 16 окт в 20:00». */
export function billboardSubtitle(startsAt: string, timeZone: string, now: number): string {
  const day = dayKey(startsAt, timeZone);
  const today = dayKey(new Date(now).toISOString(), timeZone);
  const diff = Math.round((Date.parse(`${day}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) / DAY_MS);
  const time = formatTime(startsAt, timeZone);
  if (diff === 0) return `Сегодня в ${time}`;
  if (diff === 1) return `Завтра в ${time}`;
  if (diff > 1 && diff <= 6) return `Уже ${THIS_WEEKDAY[new Date(`${day}T12:00:00Z`).getUTCDay()]}`;
  return `${formatDate(startsAt, timeZone)} в ${time}`;
}
