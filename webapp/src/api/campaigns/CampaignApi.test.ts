import { describe, expect, it } from 'vitest';
import { OwnerApiError } from '../owner/OwnerApi';
import { MSG } from '../owner/messages';
import { QuietHoursError, parseCampaignError } from './CampaignApi';
import { CMSG } from './messages';

describe('parseCampaignError', () => {
  it('turns the night answer into QuietHoursError with the suggested time', () => {
    const error = parseCampaignError(422, {
      field: 'at',
      message: CMSG.night,
      suggestedAt: '2026-10-11T07:00:00+00:00',
    });
    expect(error).toBeInstanceOf(QuietHoursError);
    expect(error).toBeInstanceOf(OwnerApiError);
    expect(error.status).toBe(422);
    expect(error.field).toBe('at');
    expect(error.message).toBe(CMSG.night);
    expect((error as QuietHoursError).suggestedAt).toBe('2026-10-11T07:00:00+00:00');
  });

  it('keeps an ordinary owner error as it is', () => {
    const error = parseCampaignError(409, { message: CMSG.stale });
    expect(error).not.toBeInstanceOf(QuietHoursError);
    expect(error.status).toBe(409);
    expect(error.message).toBe(CMSG.stale);
    expect(error.field).toBeNull();
  });

  it('reads the field of a content error', () => {
    const error = parseCampaignError(422, { field: 'eventId', message: CMSG.eventNotPublished });
    expect(error.field).toBe('eventId');
  });

  it('maps a bare FastAPI detail by status', () => {
    expect(parseCampaignError(403, { detail: 'Forbidden' }).message).toBe(MSG.noAccess);
  });
});
