/** Local-only sign-in: same gate UI, no Auth0 (set in root `.env` for Vite). */
export function isDevFakeAuthEnabled(): boolean {
  const v = String(import.meta.env.VITE_DEV_FAKE_AUTH ?? "").trim().toLowerCase();
  return v === "1" || v === "true" || v === "yes" || v === "on";
}

export const DEV_FAKE_AUTH_STORAGE_KEY = "overfished_dev_fake_auth";
