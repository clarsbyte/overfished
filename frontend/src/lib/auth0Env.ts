/** True when all Auth0 Vite env vars are set (non-blank). */
export function isAuth0Configured(): boolean {
  const d = String(import.meta.env.VITE_AUTH0_DOMAIN ?? "").trim();
  const c = String(import.meta.env.VITE_AUTH0_CLIENT_ID ?? "").trim();
  const a = String(import.meta.env.VITE_AUTH0_AUDIENCE ?? "").trim();
  return Boolean(d && c && a);
}
