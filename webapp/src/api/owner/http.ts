import { MSG } from './messages';
import { OwnerApiError } from './OwnerApi';

export type OwnerCall = <T>(method: string, path: string, body?: unknown, form?: FormData) => Promise<T>;

/** A fetch to /api/owner*: same origin as the Mini App (Caddy), signed in with Telegram initData. */
export function ownerCall(
  initData: () => string,
  base: string,
  parseError: (status: number, body: unknown) => OwnerApiError,
): OwnerCall {
  return async <T,>(method: string, path: string, body?: unknown, form?: FormData): Promise<T> => {
    const headers: Record<string, string> = { Authorization: `tma ${initData()}` };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    let res: Response;
    try {
      res = await fetch(`${base}${path}`, {
        method,
        headers,
        body: form ?? (body === undefined ? undefined : JSON.stringify(body)),
      });
    } catch {
      throw new OwnerApiError(0, MSG.network);
    }
    let data: unknown = null;
    try {
      data = await res.json();
    } catch {
      // empty or non-JSON body
    }
    if (!res.ok) throw parseError(res.status, data);
    return data as T;
  };
}
