import { CMSG } from '../../api/campaigns/messages';
import type { CampaignButton, ImageKind } from '../../api/campaigns/types';
import { telegramLength, textLimit, visibleText } from './text';

/** The server's content checks (src/services/campaigns/content.py): same order, same texts. */

export const MAX_BUTTONS = 2;
export const LABEL_LIMIT = 40;
export const URL_LIMIT = 2048;
export const TITLE_LIMIT = 256;

export interface RuleError {
  field: 'body' | 'buttons';
  message: string;
}

const TOKEN = /<(\/?)([^\s>/]*)([^>]*)>|&([^;\s<&]*);|[^<&]+|[<&]/g;
const ENTITY = /^(lt|gt|amp|quot|#\d+|#x[0-9a-f]+)$/i;

/** Only <b>, <i> and <a href="https://…"> nested properly; no bare <, > or &. */
function htmlError(body: string): RuleError | null {
  const open: string[] = [];
  const onlyTags = { field: 'body', message: CMSG.onlyTags } as const;
  for (const [token, closing, tag, attrs, entity] of body.matchAll(TOKEN)) {
    if (entity !== undefined) {
      if (!ENTITY.test(entity)) return onlyTags;
    } else if (tag !== undefined) {
      if (closing) {
        if (attrs.trim() || open.pop() !== tag) return onlyTags;
      } else if ((tag === 'b' || tag === 'i') && !attrs) {
        open.push(tag);
      } else if (tag === 'a' && !open.includes('a')) {
        const href = /^ href="([^"]*)"$/.exec(attrs);
        if (!href) return onlyTags;
        if (!href[1].startsWith('https://')) return { field: 'body', message: CMSG.httpsOnly };
        open.push(tag);
      } else {
        return onlyTags;
      }
    } else if (/[<>&]/.test(token)) {
      return onlyTags;
    }
  }
  return open.length ? onlyTags : null;
}

/** An empty text is fine in a draft and a template; sending needs one. */
export function bodyError(
  body: string,
  imageKind: ImageKind,
  { allowEmpty }: { allowEmpty: boolean },
): RuleError | null {
  if (!body && allowEmpty) return null;
  const html = htmlError(body);
  if (html) return html;
  if (!visibleText(body).trim()) return { field: 'body', message: CMSG.emptyBody };
  if (telegramLength(body) > textLimit(imageKind)) return { field: 'body', message: CMSG.tooLong };
  return null;
}

export function buttonsError(buttons: CampaignButton[], hasEvent: boolean): RuleError | null {
  if (buttons.length > MAX_BUTTONS) return { field: 'buttons', message: CMSG.tooManyButtons };
  for (const button of buttons) {
    const label = button.label.trim();
    if (label.length < 1 || label.length > LABEL_LIMIT) {
      return { field: 'buttons', message: CMSG.badLabel };
    }
    if (button.kind === 'event') {
      if (!hasEvent) return { field: 'buttons', message: CMSG.pickEvent };
    } else if (!button.url.startsWith('https://') || button.url.length > URL_LIMIT) {
      return { field: 'buttons', message: CMSG.httpsOnly };
    }
  }
  return null;
}

export function trimButtons(buttons: CampaignButton[]): CampaignButton[] {
  return buttons.map((b) => (b.kind === 'event' ? { kind: 'event', label: b.label.trim() } : { ...b, label: b.label.trim() }));
}
