/**
 * Injected by {@link Auth0TokenBridge} under Auth0Provider. Used by api.ts / agentApi.ts
 * so we do not thread tokens through every hook and callsite.
 */
export type AccessTokenGetter = () => Promise<string | undefined>;

let getAccessTokenFromProvider: AccessTokenGetter | null = null;

export function setAccessTokenGetter(fn: AccessTokenGetter | null): void {
  getAccessTokenFromProvider = fn;
}

export async function getAccessTokenForApi(): Promise<string | undefined> {
  if (!getAccessTokenFromProvider) return undefined;
  return getAccessTokenFromProvider();
}

function mergeHeaders(
  init: RequestInit | undefined,
  extra: Record<string, string>,
): RequestInit {
  const h = new Headers(init?.headers);
  for (const [k, v] of Object.entries(extra)) {
    h.set(k, v);
  }
  return { ...init, headers: h };
}

export async function buildAuthFetchOptions(init?: RequestInit): Promise<RequestInit> {
  const t = await getAccessTokenForApi();
  if (!t) return init ?? {};
  return mergeHeaders(init, { Authorization: `Bearer ${t}` });
}
