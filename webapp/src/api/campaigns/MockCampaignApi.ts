import { bodyError, buttonsError, TITLE_LIMIT, trimButtons } from '../../owner/campaigns/rules';
import { MSG } from '../owner/messages';
import { MAX_PHOTO_BYTES, PHOTO_TYPES, type OwnerRole } from '../owner/MockOwnerApi';
import { OwnerApiError } from '../owner/OwnerApi';
import { QuietHoursError, type CampaignApi } from './CampaignApi';
import { buildCampaignFixtures, zeroStats, type CampaignFixtures } from './campaignFixtures';
import { CMSG } from './messages';
import type {
  AudienceCount,
  AudienceFilter,
  Campaign,
  CampaignButton,
  CampaignFilter,
  CampaignInput,
  CampaignListItem,
  CampaignPatch,
  CampaignStats,
  CampaignTemplate,
  ImageKind,
  TemplateInput,
} from './types';

interface MockCampaignApiOptions {
  role?: OwnerRole;
  now?: () => number;
  latencyMs?: number;
  offline?: boolean;
  fixtures?: CampaignFixtures;
  /** false: the owner never opened the bot, so "send to myself" cannot reach them. */
  telegramLinked?: boolean;
}

const MSK_OFFSET_MS = 3 * 60 * 60 * 1000;
const NAME_LIMIT = 128;
const IMAGE_KINDS: ImageKind[] = ['event', 'upload', 'none'];
const SENT = new Set(['running', 'completed', 'stopped', 'cancelled']);
const PHOTO_NAME = /\.(jpe?g|png|webp|heic|heif)$/i;

const fieldError = (field: string, message: string) => new OwnerApiError(422, message, field);

/** 22:00–10:00 Moscow time (src/services/campaigns/launch.py). */
function mskHour(t: number): number {
  return new Date(t + MSK_OFFSET_MS).getUTCHours();
}

function isQuiet(t: number): boolean {
  const hour = mskHour(t);
  return hour >= 22 || hour < 10;
}

function nextMorning(t: number): string {
  const local = new Date(t + MSK_OFFSET_MS);
  const day = local.getUTCDate() + (local.getUTCHours() < 10 ? 0 : 1);
  return new Date(Date.UTC(local.getUTCFullYear(), local.getUTCMonth(), day, 10) - MSK_OFFSET_MS).toISOString();
}

/** Versions and ISO times share their first 23 characters' meaning: a moment to the millisecond. */
const momentOf = (iso: string) => Date.parse(`${iso.slice(0, 23)}Z`);

/** In-memory /api/owner/campaigns* with the server's rules and texts (CMSG). */
export class MockCampaignApi implements CampaignApi {
  readonly role: OwnerRole;
  private readonly now: () => number;
  private readonly latencyMs: number;
  private readonly offline: boolean;
  private readonly telegramLinked: boolean;
  private readonly data: CampaignFixtures;
  private seq = 0;
  private version = 0;

  constructor(options: MockCampaignApiOptions = {}) {
    this.role = options.role ?? 'owner';
    this.now = options.now ?? Date.now;
    this.latencyMs = options.latencyMs ?? 300;
    this.offline = options.offline ?? false;
    this.telegramLinked = options.telegramLinked ?? true;
    this.data = options.fixtures ?? buildCampaignFixtures(this.now());
    for (const c of this.data.campaigns) c.updatedAt = this.stamp();
  }

  campaigns(filter: CampaignFilter): Promise<CampaignListItem[]> {
    return this.call(() => {
      const all = this.data.campaigns;
      let picked: Campaign[];
      if (filter === 'draft') {
        picked = all.filter((c) => c.status === 'draft').sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
      } else if (filter === 'scheduled') {
        picked = all
          .filter((c) => c.status === 'scheduled')
          .sort((a, b) => Date.parse(a.scheduledAt ?? '') - Date.parse(b.scheduledAt ?? ''));
      } else {
        const when = (c: Campaign) => momentOf(c.startedAt ?? c.updatedAt);
        picked = all.filter((c) => SENT.has(c.status)).sort((a, b) => when(b) - when(a));
      }
      return picked.map((c) => {
        const stats = this.data.stats[c.id];
        return { ...this.out(c), delivered: stats?.delivered ?? 0, clicked: stats?.clicked ?? 0 };
      });
    });
  }

  audienceCount(filter: AudienceFilter): Promise<AudienceCount> {
    return this.call(() => this.count(filter));
  }

  campaign(id: string): Promise<Campaign> {
    return this.call(() => this.out(this.find(id)));
  }

  stats(id: string): Promise<CampaignStats> {
    return this.call(() => {
      const c = this.find(id);
      return structuredClone(this.data.stats[id] ?? zeroStats(c.eventId ? 0 : null));
    });
  }

  createCampaign(input: CampaignInput): Promise<Campaign> {
    return this.call(() => {
      this.seq += 1;
      const c: Campaign = {
        id: `c-new-${this.seq}`,
        title: CMSG.defaultTitle,
        body: '',
        image: { kind: 'none' },
        buttons: [],
        eventId: null,
        audience: { event: null, directionId: null, purchases: 'any' },
        status: 'draft',
        scheduledAt: null,
        startedAt: null,
        finishedAt: null,
        recipientCount: null,
        cancelReason: null,
        updatedAt: '',
      };
      this.apply(c, input);
      c.updatedAt = this.stamp();
      this.data.campaigns.push(c);
      return this.out(c);
    });
  }

  updateCampaign(id: string, patch: CampaignPatch): Promise<Campaign> {
    return this.call(() => {
      const c = this.editable(id);
      if (patch.updatedAt !== c.updatedAt) throw new OwnerApiError(409, CMSG.stale);
      const { updatedAt: _, ...values } = patch;
      this.apply(c, values);
      c.updatedAt = this.stamp();
      return this.out(c);
    });
  }

  duplicate(id: string): Promise<Campaign> {
    return this.call(() => {
      const source = this.find(id);
      this.seq += 1;
      const copy: Campaign = {
        ...structuredClone(source),
        id: `c-new-${this.seq}`,
        title: source.title.slice(0, TITLE_LIMIT - CMSG.copySuffix.length) + CMSG.copySuffix,
        status: 'draft',
        scheduledAt: null,
        startedAt: null,
        finishedAt: null,
        recipientCount: null,
        cancelReason: null,
        updatedAt: this.stamp(),
      };
      this.data.campaigns.push(copy);
      return this.out(copy);
    });
  }

  uploadImage(id: string, file: File): Promise<Campaign> {
    return this.call(() => {
      const c = this.editable(id);
      if (file.size > MAX_PHOTO_BYTES) throw new OwnerApiError(413, MSG.photoTooBig, 'image');
      const typed = file.type ? PHOTO_TYPES.includes(file.type) : PHOTO_NAME.test(file.name);
      if (!typed) throw new OwnerApiError(415, MSG.notAPhoto, 'image');
      this.check(bodyError(c.body, 'upload', { allowEmpty: true }));
      this.seq += 1;
      const url = typeof URL.createObjectURL === 'function' ? URL.createObjectURL(file) : './mock/kino.jpg';
      c.image = { kind: 'upload', ref: `campaigns/mock-${this.seq}.jpg`, url };
      c.updatedAt = this.stamp();
      return this.out(c);
    });
  }

  clearImage(id: string): Promise<Campaign> {
    return this.call(() => {
      const c = this.editable(id);
      c.image = { kind: 'none' };
      c.updatedAt = this.stamp();
      return this.out(c);
    });
  }

  send(id: string, at: string | null): Promise<Campaign> {
    return this.call(() => {
      const c = this.find(id);
      if (c.status !== 'draft') throw new OwnerApiError(422, CMSG.locked);
      this.check(bodyError(c.body, c.image.kind, { allowEmpty: false }));
      this.check(buttonsError(c.buttons, c.eventId !== null));
      if (c.eventId !== null && this.event(c.eventId)?.status !== 'published') {
        throw fieldError('eventId', CMSG.eventGone);
      }
      const { count } = this.count(c.audience);
      if (count === 0) throw fieldError('audience', CMSG.noRecipients);
      const now = this.now();
      if (at === null) {
        if (isQuiet(now)) throw new QuietHoursError(CMSG.night, nextMorning(now));
        Object.assign(c, { status: 'running', startedAt: new Date(now).toISOString(), recipientCount: count });
        this.data.stats[c.id] = { ...zeroStats(c.eventId ? 0 : null), recipients: count };
      } else {
        const when = Date.parse(at);
        if (when <= now) throw fieldError('at', CMSG.past);
        if (isQuiet(when)) throw fieldError('at', CMSG.quietAt);
        Object.assign(c, { status: 'scheduled', scheduledAt: new Date(when).toISOString() });
      }
      c.updatedAt = this.stamp();
      return this.out(c);
    });
  }

  cancel(id: string): Promise<Campaign> {
    return this.call(() => {
      const c = this.find(id);
      if (c.status !== 'scheduled') throw new OwnerApiError(422, CMSG.cancelOnlyScheduled);
      c.status = 'cancelled';
      c.updatedAt = this.stamp();
      return this.out(c);
    });
  }

  stop(id: string): Promise<Campaign> {
    return this.call(() => {
      const c = this.find(id);
      if (c.status !== 'running') throw new OwnerApiError(422, CMSG.stopOnlyRunning);
      Object.assign(c, { status: 'stopped', finishedAt: new Date(this.now()).toISOString() });
      c.updatedAt = this.stamp();
      return this.out(c);
    });
  }

  sendTest(id: string): Promise<void> {
    return this.call(() => {
      const c = this.find(id);
      if (!this.telegramLinked) throw new OwnerApiError(422, CMSG.botBlocked);
      if (!c.body) throw fieldError('body', CMSG.emptyBody);
      if (c.eventId === null && c.buttons.some((b) => b.kind === 'event')) {
        throw new OwnerApiError(422, CMSG.pickEvent);
      }
    });
  }

  saveAsTemplate(campaignId: string, name: string): Promise<CampaignTemplate> {
    return this.call(() => {
      const c = this.find(campaignId);
      return this.addTemplate({ name, body: c.body, imageKind: c.image.kind, buttons: c.buttons });
    });
  }

  templates(): Promise<CampaignTemplate[]> {
    return this.call(() =>
      structuredClone(this.data.templates).sort(
        (a, b) =>
          Number(b.isBuiltin) - Number(a.isBuiltin) ||
          b.updatedAt.localeCompare(a.updatedAt) ||
          a.name.localeCompare(b.name, 'ru'),
      ),
    );
  }

  createTemplate(input: TemplateInput): Promise<CampaignTemplate> {
    return this.call(() => this.addTemplate(input));
  }

  updateTemplate(id: string, input: TemplateInput): Promise<CampaignTemplate> {
    return this.call(() => {
      const t = this.ownTemplate(id);
      Object.assign(t, this.checkTemplate({ ...t, ...input }), { updatedAt: this.stamp() });
      return structuredClone(t);
    });
  }

  deleteTemplate(id: string): Promise<void> {
    return this.call(() => {
      const t = this.ownTemplate(id);
      this.data.templates = this.data.templates.filter((x) => x !== t);
    });
  }

  private async call<T>(fn: () => T): Promise<T> {
    if (this.latencyMs > 0) await new Promise((resolve) => setTimeout(resolve, this.latencyMs));
    if (this.offline) throw new OwnerApiError(0, MSG.network);
    // Door staff and guests have no manage_campaigns.
    if (this.role !== 'owner') throw new OwnerApiError(403, MSG.noAccess);
    return fn();
  }

  private stamp(): string {
    this.version += 1;
    return `${new Date(this.now()).toISOString().slice(0, 23)}${String(this.version).padStart(3, '0')}+00:00`;
  }

  private check(error: { field: string; message: string } | null): void {
    if (error) throw fieldError(error.field, error.message);
  }

  private event(id: string) {
    return this.data.events.find((e) => e.id === id);
  }

  private find(id: string): Campaign {
    const c = this.data.campaigns.find((x) => x.id === id);
    if (!c) throw new OwnerApiError(404, CMSG.campaignNotFound);
    return c;
  }

  private editable(id: string): Campaign {
    const c = this.find(id);
    if (c.status !== 'draft' && c.status !== 'scheduled') throw new OwnerApiError(422, CMSG.locked);
    return c;
  }

  /** `_apply` of src/services/campaigns/owner.py: checks the campaign as it will be after the change. */
  private apply(c: Campaign, values: CampaignInput): void {
    const title = (values.title ?? c.title).trim();
    if (!title) throw fieldError('title', CMSG.emptyTitle);
    const eventId = values.eventId !== undefined ? values.eventId : c.eventId;
    if (values.eventId != null && this.event(values.eventId)?.status !== 'published') {
      throw fieldError('eventId', CMSG.eventNotPublished);
    }
    const image = values.image ? { kind: values.image.kind } : c.image;
    if (image.kind === 'event' && eventId === null) throw fieldError('image', CMSG.pickEvent);
    const buttons = values.buttons ?? c.buttons;
    this.check(buttonsError(buttons, eventId !== null));
    const body = values.body ?? c.body;
    this.check(bodyError(body, image.kind, { allowEmpty: true }));
    Object.assign(c, { title: title.slice(0, TITLE_LIMIT), eventId, image, buttons: trimButtons(buttons), body });
    if (values.audience) c.audience = structuredClone(values.audience);
  }

  /** Server-side shape: the event image carries the event's cover. */
  private out(c: Campaign): Campaign {
    const copy = structuredClone(c);
    if (c.image.kind === 'event') {
      copy.image = { kind: 'event', url: c.eventId ? (this.event(c.eventId)?.posterUrl ?? null) : null };
    }
    return copy;
  }

  /** Deterministic stand-in for the segment: numbers the screens and tests can rely on. */
  private count(filter: AudienceFilter): AudienceCount {
    let n = 223;
    if (filter.event) {
      const event = this.event(filter.event.id);
      const relation = filter.event.relation;
      n = !event ? 0 : relation === 'liked' ? 37 : relation === 'liked_not_bought' ? 19 : event.sold;
    }
    if (filter.directionId) n = Math.round(n / 2);
    if (filter.purchases === 'bought') n = Math.round(n * 0.6);
    if (filter.purchases === 'never') n -= Math.round(n * 0.6);
    const overLimit = n >= 100 ? 9 : 0;
    return { count: n - overLimit, overLimit };
  }

  private ownTemplate(id: string): CampaignTemplate {
    const t = this.data.templates.find((x) => x.id === id);
    if (!t) throw new OwnerApiError(404, CMSG.templateNotFound);
    if (t.isBuiltin) throw new OwnerApiError(403, CMSG.builtinLocked);
    return t;
  }

  /** `_apply` of src/services/campaigns/templates.py; an event button is fine in a template. */
  private checkTemplate(input: TemplateInput): Required<TemplateInput> {
    const name = (input.name ?? '').trim();
    if (!name) throw fieldError('name', CMSG.emptyName);
    const imageKind = input.imageKind ?? 'none';
    if (!IMAGE_KINDS.includes(imageKind)) throw fieldError('imageKind', CMSG.badImage);
    const buttons: CampaignButton[] = input.buttons ?? [];
    this.check(buttonsError(buttons, true));
    const body = input.body ?? '';
    this.check(bodyError(body, imageKind, { allowEmpty: true }));
    return { name: name.slice(0, NAME_LIMIT), body, imageKind, buttons: trimButtons(buttons) };
  }

  private addTemplate(input: TemplateInput): CampaignTemplate {
    this.seq += 1;
    const t: CampaignTemplate = {
      id: `t-new-${this.seq}`,
      ...this.checkTemplate(input),
      isBuiltin: false,
      updatedAt: this.stamp(),
    };
    this.data.templates.push(t);
    return structuredClone(t);
  }
}
