import type { ImageKind } from '../../api/campaigns/types';
import { CLUB_TIMEZONE } from '../form';

/*
 * The owner writes markup the way Telegram users do: **bold**, __italic__, [label](https://…).
 * The API takes Telegram HTML, where <, > and & in the text must be entities.
 */

export const CAPTION_LIMIT = 1024;
export const MESSAGE_LIMIT = 4096;

export const PLACEHOLDERS = ['{event}', '{date}'] as const;

const LINK = /\[([^\]\n]+)\]\((https:\/\/[^\s)"<>]+)\)/y;
const MARKERS: Record<string, 'b' | 'i'> = { '**': 'b', __: 'i' };

function escapeText(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/**
 * Markers toggle with a stack: one closes only the innermost open marker of its kind.
 * A marker that would cross another, an unclosed one and an empty pair stay literal text.
 */
export function markupToHtml(markup: string): string {
  const out: string[] = [];
  const open: { tag: 'b' | 'i'; at: number }[] = [];
  let text = '';
  const flush = () => {
    if (text) out.push(escapeText(text));
    text = '';
  };
  let i = 0;
  while (i < markup.length) {
    LINK.lastIndex = i;
    const link = LINK.exec(markup);
    if (link) {
      flush();
      out.push(`<a href="${escapeText(link[2])}">${escapeText(link[1])}</a>`);
      i += link[0].length;
      continue;
    }
    const marker = markup.slice(i, i + 2);
    const tag = MARKERS[marker];
    if (!tag) {
      text += markup[i];
      i += 1;
      continue;
    }
    flush();
    const top = open[open.length - 1];
    if (top?.tag === tag && top.at < out.length - 1) {
      open.pop();
      out[top.at] = `<${tag}>`;
      out.push(`</${tag}>`);
    } else if (open.some((o) => o.tag === tag)) {
      out.push(marker);
    } else {
      open.push({ tag, at: out.length });
      out.push(marker);
    }
    i += 2;
  }
  flush();
  return out.join('');
}

function decodeEntities(text: string): string {
  return text.replace(/&(#x[0-9a-f]+|#\d+|lt|gt|amp|quot);/gi, (entity: string, name: string) => {
    const lower = name.toLowerCase();
    if (lower === 'lt') return '<';
    if (lower === 'gt') return '>';
    if (lower === 'amp') return '&';
    if (lower === 'quot') return '"';
    const code = lower.startsWith('#x') ? parseInt(lower.slice(2), 16) : parseInt(lower.slice(1), 10);
    return code <= 0x10ffff ? String.fromCodePoint(code) : entity;
  });
}

/** Back from the server's HTML (ours or a template's) to the editor's markup. */
export function htmlToMarkup(html: string): string {
  return html.replace(
    /<a href="([^"]*)">([\s\S]*?)<\/a>|<\/?b>|<\/?i>|<[^>]*>|[^<]+/gi,
    (token: string, href?: string, label?: string) => {
      if (href !== undefined) return `[${visibleText(label ?? '')}](${decodeEntities(href)})`;
      if (/^<\/?b>$/i.test(token)) return '**';
      if (/^<\/?i>$/i.test(token)) return '__';
      if (token.startsWith('<')) return '';
      return decodeEntities(token);
    },
  );
}

export function visibleText(html: string): string {
  return decodeEntities(html.replace(/<[^>]*>/g, ''));
}

/** Telegram measures in UTF-16 code units, as JS strings do: an emoji takes two. */
export function telegramLength(html: string): number {
  return visibleText(html).length;
}

export function textLimit(imageKind: ImageKind): number {
  return imageKind === 'none' ? MESSAGE_LIMIT : CAPTION_LIMIT;
}

export function hasPlaceholders(text: string): boolean {
  return PLACEHOLDERS.some((p) => text.includes(p));
}

const DAY_MONTH = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'long',
  timeZone: CLUB_TIMEZONE,
});

export function fillPlaceholders(markup: string, event: { title: string; startsAt: string }): string {
  return markup
    .split('{event}')
    .join(event.title)
    .split('{date}')
    .join(DAY_MONTH.format(new Date(event.startsAt)));
}
