import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';
import { TgProvider } from '../telegram/hooks';
import { createTg } from '../telegram/tg';
import { parseFavorites, useFavorites } from './favorites';

beforeEach(() => localStorage.clear());

describe('parseFavorites', () => {
  it('treats garbage as an empty list', () => {
    expect(parseFavorites(null)).toEqual([]);
    expect(parseFavorites('oops')).toEqual([]);
    expect(parseFavorites('{"a":1}')).toEqual([]);
    expect(parseFavorites('[1, 2]')).toEqual([]);
  });

  it('drops duplicates and keeps the last hundred', () => {
    expect(parseFavorites('["a","b","a"]')).toEqual(['a', 'b']);
    const many = parseFavorites(JSON.stringify(Array.from({ length: 150 }, (_, i) => 'e' + i)));
    expect(many).toHaveLength(100);
    expect(many[0]).toBe('e50');
  });
});

describe('useFavorites', () => {
  it('toggles an event in and out and writes CloudStorage', async () => {
    const tg = createTg();
    const client = new QueryClient();
    const wrapper = ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client }, createElement(TgProvider, { value: tg, children }));
    const { result } = renderHook(() => useFavorites(), { wrapper });
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.ids).toEqual([]);

    act(() => result.current.toggle('e-film'));
    await waitFor(() => expect(result.current.has('e-film')).toBe(true));
    await waitFor(async () => expect(await tg.storage.get('fav')).toBe('["e-film"]'));

    act(() => result.current.toggle('e-film'));
    await waitFor(() => expect(result.current.ids).toEqual([]));
    await waitFor(async () => expect(await tg.storage.get('fav')).toBe('[]'));
  });
});
