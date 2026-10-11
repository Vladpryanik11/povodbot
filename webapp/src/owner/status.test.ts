import { describe, expect, it } from 'vitest';
import type { Poster } from '../api/types';
import { ownerStatus } from './status';

const P: Poster = { url: './mock/kino.jpg', focusX: 0.5, focusY: 0.4, width: 800, height: 1000 };

describe('ownerStatus', () => {
  it('names live evenings with their sales and drafts with what they lack', () => {
    expect(ownerStatus({ status: 'published', sold: 18, capacity: 30, poster: P }, false)).toEqual({
      text: 'Опубликовано · 18/30',
      tone: 'success',
    });
    expect(ownerStatus({ status: 'draft', sold: 0, capacity: 30, poster: P }, false).text).toBe('Черновик');
    expect(ownerStatus({ status: 'draft', sold: 0, capacity: 30, poster: null }, false)).toEqual({
      text: 'Черновик · нет фото',
      tone: 'warning',
    });
  });

  it('names past evenings by how they ended', () => {
    expect(ownerStatus({ status: 'completed', sold: 25, capacity: 30, poster: P }, true).text).toBe('Прошёл · 25/30');
    expect(ownerStatus({ status: 'published', sold: 25, capacity: 30, poster: P }, true).text).toBe('Прошёл · 25/30');
    expect(ownerStatus({ status: 'cancelled', sold: 0, capacity: 30, poster: P }, true).text).toBe('Отменён');
  });
});
