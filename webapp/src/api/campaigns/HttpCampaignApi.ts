import { ownerCall, type OwnerCall } from '../owner/http';
import { parseCampaignError, type CampaignApi } from './CampaignApi';
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

/** Real /api/owner/campaigns* client, see the contract in CampaignApi.ts. */
export class HttpCampaignApi implements CampaignApi {
  private readonly call: OwnerCall;

  constructor(initData: () => string, base = '/api/owner') {
    this.call = ownerCall(initData, base, parseCampaignError);
  }

  campaigns(filter: CampaignFilter) {
    return this.call<CampaignListItem[]>('GET', `/campaigns?filter=${filter}`);
  }
  audienceCount(filter: AudienceFilter) {
    return this.call<AudienceCount>('POST', '/campaigns/audience-count', filter);
  }
  campaign(id: string) {
    return this.call<Campaign>('GET', `/campaigns/${id}`);
  }
  stats(id: string) {
    return this.call<CampaignStats>('GET', `/campaigns/${id}/stats`);
  }
  createCampaign(input: CampaignInput) {
    return this.call<Campaign>('POST', '/campaigns', input);
  }
  updateCampaign(id: string, patch: CampaignPatch) {
    return this.call<Campaign>('PATCH', `/campaigns/${id}`, patch);
  }
  duplicate(id: string) {
    return this.call<Campaign>('POST', `/campaigns/${id}/duplicate`);
  }
  uploadImage(id: string, file: File) {
    const form = new FormData();
    form.append('file', file);
    return this.call<Campaign>('POST', `/campaigns/${id}/image`, undefined, form);
  }
  clearImage(id: string) {
    return this.call<Campaign>('DELETE', `/campaigns/${id}/image`);
  }
  send(id: string, at: string | null) {
    return this.call<Campaign>('POST', `/campaigns/${id}/send`, at === null ? {} : { at });
  }
  cancel(id: string) {
    return this.call<Campaign>('POST', `/campaigns/${id}/cancel`);
  }
  stop(id: string) {
    return this.call<Campaign>('POST', `/campaigns/${id}/stop`);
  }
  async sendTest(id: string) {
    await this.call<null>('POST', `/campaigns/${id}/test`);
  }
  saveAsTemplate(campaignId: string, name: string) {
    return this.call<CampaignTemplate>('POST', `/campaigns/${campaignId}/save-as-template`, { name });
  }
  templates() {
    return this.call<CampaignTemplate[]>('GET', '/campaign-templates');
  }
  createTemplate(input: TemplateInput) {
    return this.call<CampaignTemplate>('POST', '/campaign-templates', input);
  }
  updateTemplate(id: string, input: TemplateInput) {
    return this.call<CampaignTemplate>('PATCH', `/campaign-templates/${id}`, input);
  }
  async deleteTemplate(id: string) {
    await this.call<null>('DELETE', `/campaign-templates/${id}`);
  }
}
