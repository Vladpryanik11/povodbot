import type { EventStatus } from '../api/owner/types';
import type { Poster } from '../api/types';
import type { PillTone } from '../ui/Pill';

interface StatusSource {
  status: EventStatus;
  sold: number;
  capacity: number;
  poster: Poster | null;
}

/** The status pill of an evening; `past` is the «Прошли» view, where a published evening has already happened. */
export function ownerStatus(item: StatusSource, past: boolean): { text: string; tone: PillTone } {
  const sales = `${item.sold}/${item.capacity}`;
  if (item.status === 'cancelled') return { text: 'Отменён', tone: 'muted' };
  if (past || item.status === 'completed') return { text: `Прошёл · ${sales}`, tone: 'muted' };
  if (item.status === 'published') return { text: `Опубликовано · ${sales}`, tone: 'success' };
  if (!item.poster) return { text: 'Черновик · нет фото', tone: 'warning' };
  return { text: 'Черновик', tone: 'muted' };
}
