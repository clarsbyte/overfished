/**
 * Land/ocean mask runtime loader.
 *
 * Loads `/sprites/land-mask.bin` (a 1024 × 512 packed-bitmap, 1 bit per
 * pixel, 1 = land). Built once via `scripts/build_land_mask.mjs` from
 * Natural Earth's `ne_110m_land` polygon set.
 *
 * Exposes a synchronous `isLand(lat, lng)` lookup once the mask has
 * loaded. Callers should `await whenReady()` before generating routes.
 */

const MASK_URL = "/sprites/land-mask.bin";
const GRID_W = 1024;
const GRID_H = 512;

let mask: Uint8Array | null = null;
let loadPromise: Promise<void> | null = null;

function startLoad(): Promise<void> {
  if (loadPromise) return loadPromise;
  loadPromise = (async () => {
    const res = await fetch(MASK_URL);
    if (!res.ok) {
      throw new Error(`Failed to load land mask: HTTP ${res.status}`);
    }
    const buf = await res.arrayBuffer();
    mask = new Uint8Array(buf);
    if (mask.length !== (GRID_W * GRID_H) / 8) {
      throw new Error(
        `land-mask.bin has wrong size: expected ${(GRID_W * GRID_H) / 8}, got ${mask.length}`,
      );
    }
  })();
  return loadPromise;
}

/** Wait for the mask to be ready. Idempotent — first call kicks off the fetch. */
export function whenLandMaskReady(): Promise<void> {
  return startLoad();
}

/**
 * Test whether a lat/lng falls on land. Returns false if the mask hasn't
 * loaded yet — callers should always `whenLandMaskReady()` first.
 */
export function isLand(lat: number, lng: number): boolean {
  if (!mask) return false;
  // Wrap longitude into [-180, 180].
  let l = lng;
  while (l > 180) l -= 360;
  while (l < -180) l += 360;
  // Clamp latitude (poles are still mappable).
  const clampedLat = Math.max(-90, Math.min(90, lat));
  const col = Math.min(
    GRID_W - 1,
    Math.max(0, Math.floor(((l + 180) / 360) * GRID_W)),
  );
  const row = Math.min(
    GRID_H - 1,
    Math.max(0, Math.floor(((90 - clampedLat) / 180) * GRID_H)),
  );
  const bitIdx = row * GRID_W + col;
  return (mask[bitIdx >> 3] & (1 << (bitIdx & 7))) !== 0;
}
