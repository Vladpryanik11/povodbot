import { useEffect, useState } from 'react';
import type { Poster } from '../api/types';
import { eventColor, extractPosterColor } from '../lib/posterColor';

type Source = { title: string; accentColor: string | null; poster: Poster | null };

/** Poster colour of an event: the organiser's pick, else read from the poster once it loads, else by title (spec v2 §3). */
export function useEventColor(source: Source | null | undefined): string | null {
  const [extracted, setExtracted] = useState<{ url: string; hex: string } | null>(null);
  const url = source && !source.accentColor ? (source.poster?.url ?? null) : null;

  useEffect(() => {
    if (!url) return;
    let live = true;
    void extractPosterColor(url).then((hex) => {
      if (live && hex) setExtracted({ url, hex });
    });
    return () => {
      live = false;
    };
  }, [url]);

  if (!source) return null;
  return eventColor(source, extracted && extracted.url === url ? extracted.hex : null);
}
