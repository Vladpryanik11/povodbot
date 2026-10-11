import { CMSG } from '../../api/campaigns/messages';
import {
  EMPTY_AUDIENCE,
  type AudienceFilter,
  type Campaign,
  type CampaignButton,
  type CampaignInput,
  type CampaignTemplate,
  type ImageKind,
} from '../../api/campaigns/types';
import { bodyError, buttonsError, trimButtons } from './rules';
import { fillPlaceholders, hasPlaceholders, htmlToMarkup, markupToHtml } from './text';

export interface CampaignForm {
  title: string;
  /** Editor markup, see text.ts. */
  markup: string;
  eventId: string | null;
  imageKind: ImageKind;
  buttons: CampaignButton[];
  audience: AudienceFilter;
  /** The template asked for the evening's poster; it is set once an evening is picked. */
  wantsPoster: boolean;
}

export type CampaignFormField = 'title' | 'eventId' | 'body' | 'image' | 'buttons' | 'audience';
export type CampaignFormErrors = Partial<Record<CampaignFormField, string>>;

export const OPEN_EVENT_BUTTON: CampaignButton = { kind: 'event', label: 'Открыть вечер' };

export function formFromCampaign(c: Campaign): CampaignForm {
  return {
    title: c.title,
    markup: htmlToMarkup(c.body),
    eventId: c.eventId,
    imageKind: c.image.kind,
    buttons: structuredClone(c.buttons),
    audience: structuredClone(c.audience),
    wantsPoster: false,
  };
}

/** A template has no evening yet: its poster and «Открыть вечер» wait until one is picked. */
export function formFromTemplate(t: CampaignTemplate | null): CampaignForm {
  if (!t) {
    return {
      title: CMSG.defaultTitle,
      markup: '',
      eventId: null,
      imageKind: 'none',
      buttons: [],
      audience: EMPTY_AUDIENCE,
      wantsPoster: false,
    };
  }
  return {
    title: t.name,
    markup: htmlToMarkup(t.body),
    eventId: null,
    imageKind: t.imageKind === 'event' ? 'none' : t.imageKind,
    buttons: t.buttons.filter((b) => b.kind !== 'event'),
    audience: EMPTY_AUDIENCE,
    wantsPoster: t.imageKind === 'event',
  };
}

/** Picking an evening fills {event} and {date}, sets the poster the template asked for, adds «Открыть вечер» to no buttons. */
export function pickEvent(
  form: CampaignForm,
  event: { id: string; title: string; startsAt: string } | null,
): CampaignForm {
  if (!event) {
    return {
      ...form,
      eventId: null,
      imageKind: form.imageKind === 'event' ? 'none' : form.imageKind,
      buttons: form.buttons.filter((b) => b.kind !== 'event'),
    };
  }
  return {
    ...form,
    eventId: event.id,
    markup: fillPlaceholders(form.markup, event),
    imageKind: form.wantsPoster && form.imageKind === 'none' ? 'event' : form.imageKind,
    buttons: form.buttons.length ? form.buttons : [OPEN_EVENT_BUTTON],
    wantsPoster: false,
  };
}

/**
 * The form as the server takes it. The uploaded image changes only by uploading, so «Своя» sends no image;
 * the evening goes only when changed, so a campaign whose evening was unpublished still saves.
 */
export function formToInput(form: CampaignForm, saved: Campaign | null): CampaignInput {
  const input: CampaignInput = {
    title: form.title.trim(),
    body: markupToHtml(form.markup),
    buttons: trimButtons(form.buttons),
    audience: form.audience,
  };
  if (form.imageKind !== 'upload') input.image = { kind: form.imageKind };
  if (!saved || saved.eventId !== form.eventId) input.eventId = form.eventId;
  return input;
}

/** The server's save checks with its texts: an empty text is fine until sending. */
export function formErrors(form: CampaignForm): CampaignFormErrors {
  const errors: CampaignFormErrors = {};
  if (!form.title.trim()) errors.title = CMSG.emptyTitle;
  if (form.imageKind === 'event' && form.eventId === null) errors.image = CMSG.pickEvent;
  const buttons = buttonsError(form.buttons, form.eventId !== null);
  if (buttons) errors.buttons = buttons.message;
  const body = bodyError(markupToHtml(form.markup), form.imageKind, { allowEmpty: true });
  if (body) errors.body = body.message;
  return errors;
}

/** What still keeps the campaign from going out, beyond formErrors. */
export function sendBlocker(form: CampaignForm): string | null {
  if (hasPlaceholders(form.markup)) return 'Выбери вечер — {event} и {date} заменятся сами';
  const body = bodyError(markupToHtml(form.markup), form.imageKind, { allowEmpty: false });
  return body ? body.message : null;
}
