import { OwnerApiError, parseOwnerError } from '../owner/OwnerApi';
import type {
  AudienceCount,
  AudienceFilter,
  Campaign,
  CampaignFilter,
  CampaignInput,
  CampaignListItem,
  CampaignPatch,
  CampaignStats,
  CampaignTemplate,
  TemplateInput,
} from './types';

/** Sending "now" at night: the server offers the next 10:00 Moscow time instead. */
export class QuietHoursError extends OwnerApiError {
  constructor(
    message: string,
    readonly suggestedAt: string,
  ) {
    super(422, message, 'at');
    this.name = 'QuietHoursError';
  }
}

/**
 * Contract of /api/owner/campaigns* (src/api/owner/campaigns.py): HttpCampaignApi in Telegram,
 * MockCampaignApi in a plain browser.
 *
 * campaigns(filter)   GET    /api/owner/campaigns?filter=draft|scheduled|sent
 * audienceCount(f)    POST   /api/owner/campaigns/audience-count       — body is the filter
 * campaign(id)        GET    /api/owner/campaigns/{id}
 * stats(id)           GET    /api/owner/campaigns/{id}/stats
 * createCampaign()    POST   /api/owner/campaigns                      — 201
 * updateCampaign()    PATCH  /api/owner/campaigns/{id}                 — body carries updatedAt
 * duplicate(id)       POST   /api/owner/campaigns/{id}/duplicate       — 201
 * uploadImage()       POST   /api/owner/campaigns/{id}/image           — multipart: file
 * clearImage(id)      DELETE /api/owner/campaigns/{id}/image
 * send(id, at)        POST   /api/owner/campaigns/{id}/send            — {at?}; none means now
 * cancel(id)          POST   /api/owner/campaigns/{id}/cancel
 * stop(id)            POST   /api/owner/campaigns/{id}/stop
 * sendTest(id)        POST   /api/owner/campaigns/{id}/test            — 204
 * saveAsTemplate()    POST   /api/owner/campaigns/{id}/save-as-template — {name}, 201
 * templates()         GET    /api/owner/campaign-templates
 * createTemplate()    POST   /api/owner/campaign-templates             — 201
 * updateTemplate()    PATCH  /api/owner/campaign-templates/{id}
 * deleteTemplate()    DELETE /api/owner/campaign-templates/{id}        — 204
 *
 * Errors reject with OwnerApiError, or QuietHoursError (see parseCampaignError).
 */
export interface CampaignApi {
  campaigns(filter: CampaignFilter): Promise<CampaignListItem[]>;
  audienceCount(filter: AudienceFilter): Promise<AudienceCount>;
  campaign(id: string): Promise<Campaign>;
  stats(id: string): Promise<CampaignStats>;
  createCampaign(input: CampaignInput): Promise<Campaign>;
  updateCampaign(id: string, patch: CampaignPatch): Promise<Campaign>;
  duplicate(id: string): Promise<Campaign>;
  uploadImage(id: string, file: File): Promise<Campaign>;
  clearImage(id: string): Promise<Campaign>;
  send(id: string, at: string | null): Promise<Campaign>;
  cancel(id: string): Promise<Campaign>;
  stop(id: string): Promise<Campaign>;
  sendTest(id: string): Promise<void>;
  saveAsTemplate(campaignId: string, name: string): Promise<CampaignTemplate>;
  templates(): Promise<CampaignTemplate[]>;
  createTemplate(input: TemplateInput): Promise<CampaignTemplate>;
  updateTemplate(id: string, input: TemplateInput): Promise<CampaignTemplate>;
  deleteTemplate(id: string): Promise<void>;
}

/** The owner error shapes, plus the night answer `{field: "at", message, suggestedAt}`. */
export function parseCampaignError(status: number, body: unknown): OwnerApiError {
  if (
    typeof body === 'object' &&
    body !== null &&
    'suggestedAt' in body &&
    typeof body.suggestedAt === 'string' &&
    'message' in body &&
    typeof body.message === 'string'
  ) {
    return new QuietHoursError(body.message, body.suggestedAt);
  }
  return parseOwnerError(status, body);
}
