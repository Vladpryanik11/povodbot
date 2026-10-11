// Shapes of /api/owner/campaigns* exactly as src/api/owner/campaign_schemas.py sends them.

export type CampaignStatus =
  | 'draft'
  | 'scheduled'
  | 'running'
  | 'completed'
  | 'cancelled'
  | 'stopped';

export type CampaignFilter = 'draft' | 'scheduled' | 'sent';

export type ImageKind = 'event' | 'upload' | 'none';

/** `upload` carries ref and url; `event` carries the event cover url; `none` neither. */
export interface CampaignImage {
  kind: ImageKind;
  ref?: string | null;
  url?: string | null;
}

export type CampaignButton =
  | { kind: 'event'; label: string }
  | { kind: 'url'; label: string; url: string };

export type AudienceRelation = 'going' | 'liked' | 'liked_not_bought' | 'attended';

export type PurchaseFilter = 'any' | 'bought' | 'never';

export interface AudienceFilter {
  event: { id: string; relation: AudienceRelation } | null;
  directionId: string | null;
  purchases: PurchaseFilter;
}

export interface Campaign {
  id: string;
  title: string;
  /** Telegram HTML: b, i, a href="https://…"; <, >, & escaped. */
  body: string;
  image: CampaignImage;
  buttons: CampaignButton[];
  eventId: string | null;
  audience: AudienceFilter;
  status: CampaignStatus;
  scheduledAt: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  recipientCount: number | null;
  cancelReason: string | null;
  /** Opaque edit version, sent back as is. */
  updatedAt: string;
}

export interface CampaignListItem extends Campaign {
  delivered: number;
  clicked: number;
}

/** An uploaded image is set only through uploadImage, so input images are event or none. */
export interface CampaignInput {
  title?: string;
  body?: string;
  image?: { kind: 'event' | 'none' };
  buttons?: CampaignButton[];
  eventId?: string | null;
  audience?: AudienceFilter;
}

export interface CampaignPatch extends CampaignInput {
  updatedAt: string;
}

export interface AudienceCount {
  count: number;
  overLimit: number;
}

export interface CampaignStats {
  recipients: number;
  delivered: number;
  failed: number;
  /** Delivery error codes (bot_blocked, recipient_not_eligible, unknown) or Telegram's own text. */
  failedReasons: Record<string, number>;
  skippedLimit: number;
  clicked: number;
  anonymousClicks: number;
  /** null when the campaign has no event. */
  bought: number | null;
}

export interface CampaignTemplate {
  id: string;
  name: string;
  body: string;
  imageKind: ImageKind;
  buttons: CampaignButton[];
  isBuiltin: boolean;
  updatedAt: string;
}

export interface TemplateInput {
  name?: string;
  body?: string;
  imageKind?: ImageKind;
  buttons?: CampaignButton[];
}

export const EMPTY_AUDIENCE: AudienceFilter = { event: null, directionId: null, purchases: 'any' };
