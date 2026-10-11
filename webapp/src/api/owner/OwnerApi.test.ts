import { describe, expect, it } from 'vitest';
import { MSG } from './messages';
import { parseOwnerError } from './OwnerApi';

describe('parseOwnerError', () => {
  it('keeps the owner error body as is', () => {
    const e = parseOwnerError(422, { field: 'capacity', message: 'Сколько мест?' });
    expect([e.status, e.field, e.message]).toEqual([422, 'capacity', 'Сколько мест?']);
    expect(parseOwnerError(409, { message: MSG.conflict }).field).toBeNull();
  });

  it('turns English detail strings into owner copy by status', () => {
    expect(parseOwnerError(401, { detail: 'Telegram sign-in required' }).message).toBe(MSG.signIn);
    expect(parseOwnerError(403, { detail: 'Admin access required' }).message).toBe(MSG.noAccess);
    expect(parseOwnerError(503, { detail: 'Telegram sign-in is not configured' }).message).toBe(MSG.unavailable);
    expect(parseOwnerError(400, { detail: 'x' }).message).toBe(MSG.unknown);
  });

  it('takes the field from a FastAPI validation error', () => {
    const e = parseOwnerError(422, { detail: [{ loc: ['body', 'capacity'], msg: 'Input should be a valid integer' }] });
    expect([e.field, e.message]).toEqual(['capacity', MSG.checkField]);
    expect(parseOwnerError(422, { detail: [{ loc: ['query', 'filter'] }] }).field).toBeNull();
  });

  it('falls back for bodies it does not know', () => {
    expect(parseOwnerError(500, '<html>').message).toBe(MSG.unknown);
    expect(parseOwnerError(500, null).field).toBeNull();
  });
});
