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
